# coding:utf-8
import asyncio,logging
import aiomysql
#设置调试级别level,此处为logging.INFO,不设置logging.info()没有任何作用等同于pass
logging.basicConfig(level=logging.DEBUG)

def log(sql,args=()):
    logging.info('SQL:%s'%sql)

# #创建数据库连接池,可以方便的从连接池中获取数据库连接,此处没什么好说的详情可以查看aiomysql的文档
# @asyncio.coroutine==async
# yield from==await
async def create_pool(loop, **kw):
    logging.info("create database connection pool...")
    '''
    此处为全局变量,相当于在函数外定义了一个变量,但是有一点区别是,函数外声明的变量一旦import导入模块,
    就声明了,在函数内部通过global声明全局变量,函数不执行,就不会创建该全局变量(这里是个人理解,总之一点global声明的变量是全局变量,
    如果在函数内部声明的,该函数不执行,在函数外部访问时,会报错,因为函数不执行,该全局变量就未被声明)
    '''
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )



async def select(sql, args, size=None):
    '''
    SQL语句的占位符是?，而MySQL的占位符是%s，select()函数在内部自动替换。注意要始终坚持使用带参数的SQL，而不是自己拼接SQL字符串，这样可以防止SQL注入攻击。
    :param sql: 
    :param args: 
    :param size: 
    :return: 
    '''
    log(sql, args)
    global __pool
    async with  __pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql.replace('?', '%s'), args or ())
            if size:
                rs = await cur.fetchmany(size)
            else:
                rs=await cur.fetchall()
        # yield from cur.close()
        logging.info('rows returned: %s'%len(rs))
        return rs


async def execute(sql,args,autocommit=True):
    '''
    execute()函数和select()函数所不同的是，cursor对象不返回结果集，而是通过rowcount返回结果数
    :param sql: 
    :param args: 
    :return: 
    '''
    log(sql)
    async with  __pool.acquire() as conn:
        if not autocommit:
            #如果不是自动提交事物，需要手动启动
            await conn.begin()
        try:
            # cur =yield from conn.cursor()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # yield from cur.execute(sql.replace('?','%s'),args)
                cur.execute(sql.replace('?', '%s'), args)
                #获取增删改影响的行数
                affected=cur.rowcount
                # yield from cur.close()
            if not autocommit:
                conn.commit()
        except BaseException as e:
            if not autocommit:
                #在执行commit()之前如果出现错误,回滚
                conn.rollback()
            raise
        return affected

#创建拥有几个占位符的字符串
def create_args_string(num):
    L=[]
    for n in range(num):
        L.append('?')
    return ', '.join(L)

#该类是为了保存数据库列名和类型的基类
class Field(object):
    def __init__(self,name,column_type,primary_key,default):
        self.name=name#列名
        self.column_type=column_type#数据类型
        self.primary_key=primary_key#是否为主键
        self.default=default#默认值

    def __str__(self):
        return '<%s, %s:%s>'%(self.__class__.__name__,self.column_type,self.name)

#一下几种是具体的列名的数据类型
class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

#元类
class ModelMetaclass(type):

    def __new__(cls, name, bases, attrs):
        #如果是基类对象,不做处理,因为没有字段名,没什么可处理的
        if name=='Model':
            return type.__new__(cls, name, bases, attrs)
        #保存表名,如果获取不到,则把类名当做表名,完美利用了or短路原理
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        #保存列类型的对象
        mappings = dict()
        #保存列名的数组
        fields = []
        #主键
        primaryKey = None
        for k, v in attrs.items():
            #是列名的就保存下来
            if isinstance(v, Field):
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    # 找到主键:
                    if primaryKey:
                        raise StandardError('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    #保存非主键的列名
                    fields.append(k)
        if not primaryKey:
            raise StandardError('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        #以下四种方法保存了默认了增删改查操作,其中添加的反引号``,是为了避免与sql关键字冲突的,否则sql语句会执行出错
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)

#这是模型的基类,继承于dict,主要作用就是如果通过点语法来访问对象的属性获取不到的话,可以定制__getattr__来通过key来再次获取字典里的值
class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        #super的另一种写法(略古老)
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        #调用getattr获取一个未存在的属性,也会走__getattr__方法,但是因为指定了默认返回的值,__getattr__里面的错误永远不会抛出
        return getattr(self, key, None)


    #使用默认值
    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    #新的语法  @classmethod装饰器用于把类里面定义的方法声明为该类的类方法
    @classmethod
    #获取表里符合条件的所有数据,类方法的第一个参数为该类名
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


    #该方法不了解
    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        ' find number by select and where. '
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']


    #主键查找的方法
    @classmethod
    async def find(cls, pk):
        ' find object by primary key. '
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])


    #一下的都是对象方法,所以可以不用传任何参数,方法内部可以使用该对象的所有属性,及其方便
    #保存实例到数据库
    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)
    #更新数据库数据
    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update by primary key: affected rows: %s' % rows)
    #删除数据
    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warn('failed to remove by primary key: affected rows: %s' % rows)



#以下为测试
loop = asyncio.get_event_loop()
loop.run_until_complete(create_pool(host='127.0.0.1', port=3306,user='root', password='123456',db='mySchool', loop=loop))
rs = loop.run_until_complete(select('select * from firstSchool',None))
#获取到了数据库返回的数据
print("heh:%s" % rs)