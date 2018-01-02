# coding:utf-8
import logging;logging.basicConfig(level=logging.DEBUG)
#设置日志
import asyncio,os,json,time
from datetime import datetime
# aiomysql为MySQL数据库提供了异步IO的驱动。
import aiomysql


from aiohttp import web

def index(request):
    #需要设置content type类型是html,否则会下载
    return web.Response(body=b'<h1>Awesome</h1>',content_type='text/html')

@asyncio.coroutine
def init(loop):
    app = web.Application(loop=loop)
    app.router.add_route('GET','/',index)
    srv = yield from loop.create_server(app.make_handler(),'127.0.0.1',8000)
    logging.info('server started at http://127.0.0.1:8000...')
    return srv



loop=asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()

