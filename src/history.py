"""Bounded, deduplicated clipboard history. Images remain inside SQLite."""
import hashlib,sqlite3,time
from pathlib import Path

def digest(kind,data):
    if isinstance(data,str):data=data.encode('utf-8')
    return hashlib.sha256(kind.encode('ascii')+b'\0'+data).hexdigest()

class History:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA secure_delete=ON');self.db.execute('PRAGMA busy_timeout=3000')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS clips (
          id INTEGER PRIMARY KEY,kind TEXT NOT NULL,digest TEXT UNIQUE NOT NULL,
          text TEXT NOT NULL DEFAULT '',image BLOB,width INTEGER NOT NULL DEFAULT 0,
          height INTEGER NOT NULL DEFAULT 0,created_ns INTEGER NOT NULL,copied_ns INTEGER NOT NULL,
          copies INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
          PRAGMA user_version=1;''')
        self.db.commit()
    def _add(self,kind,text='',image=None,width=0,height=0):
        data=text if kind=='text' else image;key=digest(kind,data);now=time.time_ns()
        self.db.execute('''INSERT INTO clips(kind,digest,text,image,width,height,created_ns,copied_ns) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(digest) DO UPDATE SET copied_ns=excluded.copied_ns,copies=clips.copies+1''',(kind,key,text,image,width,height,now,now))
        self.db.execute('DELETE FROM clips WHERE id NOT IN (SELECT id FROM clips ORDER BY copied_ns DESC,id DESC LIMIT 50)');self.db.commit()
        return self.db.execute('SELECT id FROM clips WHERE digest=?',(key,)).fetchone()[0]
    def add_text(self,text):
        if not isinstance(text,str):raise ValueError('文本类型无效。')
        if not text:return None
        if len(text.encode('utf-8'))>1024*1024:raise ValueError('文本超过 1 MiB，已跳过记录。')
        return self._add('text',text=text)
    def add_image(self,image,width,height):
        if not image:return None
        if len(image)>20*1024*1024:raise ValueError('图片超过 20 MiB，已跳过记录。')
        if width<1 or height<1:raise ValueError('图片尺寸无效。')
        return self._add('image',image=image,width=width,height=height)
    def items(self,query='',kind='all'):
        params=[];conditions=[]
        if kind in ('text','image'):conditions.append('kind=?');params.append(kind)
        if query:conditions.append('instr(lower(text),lower(?))>0');params.append(query)
        where=' WHERE '+' AND '.join(conditions) if conditions else ''
        return [dict(r) for r in self.db.execute('SELECT id,kind,substr(text,1,300) text,width,height,created_ns,copied_ns,copies,length(image) image_size FROM clips'+where+' ORDER BY copied_ns DESC,id DESC',params)]
    def get(self,id):
        row=self.db.execute('SELECT * FROM clips WHERE id=?',(id,)).fetchone();return dict(row) if row else None
    def delete(self,id):self.db.execute('DELETE FROM clips WHERE id=?',(id,));self.db.commit()
    def clear(self):
        self.db.execute('DELETE FROM clips');self.db.commit();self.db.execute('VACUUM');self.db.commit()
    def setting(self,key,value=None):
        if value is None:
            row=self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone();return row[0] if row else None
        self.db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value)));self.db.commit()
    def close(self):self.db.close()
