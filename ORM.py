import asyncio
import aiomysql
import logging
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)
format = logging.Formatter("%(asctime)s - %(message)s")    # output format
sh = logging.StreamHandler(stream=sys.stdout)    # output to standard output
sh.setFormatter(format)
logger.addHandler(sh)

def log(sql,args=()):
    global logger
    logger.info('SQL: %s'%sql)

#创建数据库链接对象
async def create_pool(loop,**kwargs):
    logger.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kwargs.get('host','localhost'),
        port=kwargs.get('port',3306),
        user=kwargs['user'],
        password=kwargs['password'],
        db=kwargs['db'],
        charset=kwargs.get('charset','utf8'),
        autocommit=kwargs.get('autocommit',True),
        loop=loop
    )

#销毁连接池
async def destory_poll():
    global __pool
    if __pool is not None:
        __pool.close()
        await __pool.wait_closed()

#创建查看方法
async def select(sql,args,size=None):
    log(sql,args)
    global __pool
    with await __pool as conn:
        #创建操作数据库的光标,返回字典格式
        cur = await conn.cursor(aiomysql.DictCursor)
        #执行一条sql语句的时候将字符中的？替换成%s,execute方法可以防止sql注入
        await cur.execute(sql.replace('?','%s'),args or ())
        if size:
            #如果传入size参数查看指定个数数据
            rs = await cur.fetchmany(size)
        else:
            #如果没有size参数则获取所有数据
            rs =await cur.fetchall()
        #关闭操作数据库的光标
        await cur.close()
        logging.info('rows returned: %s'%len(rs))
        return rs

#该函数执行增删改
async def execute(sql,args):
    log(sql)
    with await __pool as conn:
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?','%s'),args)
            #返回结果数
            affected = cur.rowcount
            await cur.close()
        except BaseException as e:
            raise
        return affected

#该类是为了保存数据库列名和类型的基类
class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        #字段名
        self.name = name
        #字段类型
        self.column_type = column_type
        #是否是主键
        self.primary_key = primary_key
        #默认值
        self.default = default

    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

#创建string字段
class StringField(Field):
    def __init__(self,name=None,primary_key=False, default=None,dll='varchar(100)'):
        super().__init__(name,dll,primary_key,default)

class BooleanField(Field):
    def __init__(self,name=None,default=False):
        super().__init__(name,'boolean',False,default)

class IntegerField(Field):
    def __init__(self,name=None,primary_key=False,default=0):
        super().__init__(name,'bigint',primary_key,default)

class FloatField(Field):
    def __init__(self,name=None,primary_key=False,default=0.0):
        super().__init__(name,'real',primary_key,default)

class TextField(Field):
    def __init__(self,name=None,default=None):
        super().__init__(name,'text',False,default)
#创建拥有几个占位符的字符串
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)

# 定义元类
class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        # 排除Model类本身:
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称表名或类名:
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table:%s)' % (name, tableName))
        # 获取所有的Field和主键名:
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            print('k',k,'v',v)
            if isinstance(v, Field):
                # logging.info(' found mapping:%s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    # 找到主键
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field:%s' % k)
                    primaryKey = k
                else:
                    #保存非主键的列
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings  # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey  # 主键属性名
        attrs['__fields__'] = fields  # 除主键外的属性名
        # 构造默认的SELECT,INSERT,UPDATE和DELETE语句：
        attrs['__select__']='select `%s`,%s from, `%s`'%(primaryKey, ', '.join(escaped_fields),tableName)
        attrs['__insert__']='insert into `%s` (%s, `%s`) values(%s)'%(tableName,', '.join(escaped_fields),primaryKey,create_args_string(len(escaped_fields)+1))
        attrs['__update__']='update `%s` set %s where `%s`=?'%(tableName,', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f),fields)),primaryKey)
        attrs['__delete__']='delete from `%s` where `%s`=?' %(tableName,primaryKey)
        return type.__new__(cls,name,bases,attrs)

# 定义基类
class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    #获取类属性
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    #写入类属性
    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s:%s' % (key, str(value)))
                setattr(self, key, value)
        return value
    # 主键查找的方法
    @classmethod
    async def find(cls,pk):
        ' find object by primary key'
        rs = await select('%s where `%s`=?'%(cls.__select__,cls.__primary_key__),[pk],1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args=list(map(self.getValueOrDefault,self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows=await execute(self.__insert__,args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s'%rows)

    # 新的语法  @classmethod装饰器用于把类里面定义的方法声明为该类的类方法
    @classmethod
    # 获取表里符合条件的所有数据,类方法的第一个参数为该类名
    async def findAll(cls, where=None, args=None, **kw):
        ' find objects by where clause. '
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]



if __name__ == '__main__':
    loop=asyncio.get_event_loop()
    # import concurrent
    # executor = concurrent.futures.ThreadPoolExecutor(5)
    # loop.set_default_executor(executor)
    loop.run_until_complete(create_pool(host='127.0.0.1',port=3306,user='root',password='mysql',db='ORM',loop=loop))
    # # import time
    # # time.sleep(1)
    # rs=loop.run_until_complete(select('select * from firstschool',None))
    # rs=loop.run_until_complete(execute('insert into  firstschool values(2,"aaa")',None))

    # print('%s'%rs)
    # class aaa(Model):
    #     id = StringField()
    #
    # aaaa = StringField()
    # print(aaaa.primary_key)


