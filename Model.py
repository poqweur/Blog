# coding:utf-8
import time,uuid

from ORM import Model,StringField,BooleanField,FloatField,TextField
#uuid设备唯一识别码
def next_id():
    return '%015d%s000'%(int(time.time()*1000),uuid.uuid4().hex)

class User(Model):
    __table__='users'

    id=StringField(dll='varchar(50)')
    passwd=StringField(dll='varchar(50)')
    admin=BooleanField()
    name=StringField(dll='varchar(50)')
    image=StringField(dll='varchar(500)')
    created_at=FloatField(default=time.time())

class Blog(Model):
    __table__='blogs'

    id = StringField(primary_key=True,default=next_id,dll='varchar(50)')
    user_id =StringField(dll='varchar(50)')
    user_name=StringField(dll='varchar(50)')
    user_image=StringField(dll='varchar(500)')
    name=StringField(dll='varchar(50)')
    summary=StringField(dll='varchar(200)')
    content=TextField()
    created_at=FloatField(default=time.time)

class Comment(Model):
    __tabale__='comments'

    id=StringField(primary_key=True,default=next_id,dll='varchar(50)')
    blog_id=StringField(dll='varchar(50)')
    user_id=StringField(dll='varchar(50)')
    user_name=StringField(dll='varchar(50)')
    user_image=StringField(dll='varchar(500)')
    content=TextField()
    created_at=FloatField(default=time.time)

