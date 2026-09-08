# === 这个文件是什么 ===
# 文件路径:petstore-api/app/main.py
# 作用:整个 Petstore 的 FastAPI 应用入口——把 schemas.py 定义的数据形状、
# crud.py 里的数据库操作,包装成外部可以用 HTTP 访问的接口(路由)。
# FastAPI 是一个 Web 框架:你写一个普通的 Python 函数,用 @app.get(...)/
# @app.post(...) 这种"装饰器"标注它对应哪个 URL 路径、哪种 HTTP 方法,
# FastAPI 就会自动帮你:解析请求参数、按类型转换和校验、调用你的函数、把
# 返回值序列化成 JSON——你在这个文件里几乎看不到手写的 JSON 解析代码,都是
# 靠类型注解"声明式"地完成的。

# collections.abc 是 Python 标准库,AsyncIterator 是一个"类型注解"专用的
# 抽象类型,表示"一个支持异步遍历的生成器"——下面 lifespan 函数的返回类型
# 会用到它。
from collections.abc import AsyncIterator
# contextlib 是 Python 标准库,asynccontextmanager 是一个装饰器,能把一个
# "普通的异步生成器函数"(带 yield 的 async def)包装成一个异步上下文管理器
# ——也就是可以用 "async with xxx():" 语法使用的东西。这里专门用来配合
# FastAPI 的 lifespan(应用生命周期)机制。
from contextlib import asynccontextmanager

# 从 fastapi 这个第三方框架库里导入四个核心工具:
#   Depends      —— 声明"依赖注入":某个参数的值应该由另一个函数算出来提供
#                    (下面用来自动获取数据库连接)
#   FastAPI      —— 应用本身的类,创建一个实例就是创建整个 Web 应用
#   HTTPException —— 用来主动抛出一个"HTTP 错误响应"(带状态码和错误信息)
#   Query        —— 给"查询参数"(URL 里 ? 后面的那部分,比如
#                    /pets?min_price_eur=100)附加额外校验规则,用法跟
#                    schemas.py 里的 Field 类似
from fastapi import Depends, FastAPI, HTTPException, Query
# fastapi.concurrency 提供的 run_in_threadpool:把一个"同步的"(不是
# async def 的)阻塞函数,丢到一个线程池里去异步执行,这样它就不会卡住整个
# 事件循环——下面用来跑数据库初始化这种同步 I/O 操作。
from fastapi.concurrency import run_in_threadpool

# 从本项目自己的 app 包里,导入 crud 模块(数据库读写逻辑)和 schemas 模块
# (上面刚读过的那个文件,数据形状定义)。用 "from app import crud, schemas"
# 这种写法导入之后,后面要用 crud.xxx()、schemas.Xxx 这样带模块名前缀地引用。
from app import crud, schemas
# 从 app/database.py 里导入:
#   Connection —— 数据库连接对象的类型(给下面函数参数做类型注解用)
#   PetRow     —— 数据库里"一行宠物记录"对应的 Python 类型
#   get_db     —— 一个函数,每次调用会拿到(或建立)一个数据库连接,
#                  配合 Depends() 使用,FastAPI 会在每个请求进来时自动调用它
#   init_db    —— 初始化数据库(建表等)的函数
from app.database import Connection, PetRow, get_db, init_db
# 从 app/models.py 里导入 Availability(库存状态)和 Species(物种)这两个
# 枚举类型,下面搜索接口的参数会用到。
from app.models import Availability, Species
# 从 app/seed.py 里导入 seed_if_empty:如果数据库是空的,就填充一些初始的
# "种子数据"(预置宠物),方便刚启动时就有数据可以看、可以搜。
from app.seed import seed_if_empty


# @asynccontextmanager:把下面这个 async def 函数,变成一个 FastAPI 能用作
# "生命周期钩子"的对象——yield 之前的代码在应用*启动时*跑一次,
# yield 之后的代码(这里没写)会在应用*关闭时*跑。
@asynccontextmanager
# lifespan:FastAPI 应用的生命周期函数。参数 app 是应用本身(这里没有用到),
# 返回类型注解 AsyncIterator[None] 表示"一个会 yield 出 None 的异步生成器"。
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # await:等待一个"可等待对象"(这里是 run_in_threadpool 返回的东西)完成。
    # run_in_threadpool(init_db):把同步函数 init_db 放到线程池里跑,
    # 且不阻塞主事件循环——应用启动时先把数据库表结构建好。
    await run_in_threadpool(init_db)
    # 同理,把"填充种子数据"这个同步函数也丢到线程池里跑一遍——
    # 如果数据库已经有数据,seed_if_empty 内部会自己判断并跳过,不会重复插入。
    await run_in_threadpool(seed_if_empty)
    # yield 这里表示:上面的启动逻辑做完了,应用现在可以开始正常处理请求了。
    # 因为 yield 后面什么都没写,并且函数体到此结束,所以"关闭时要做的清理逻辑"
    # 这里其实是空的——没有需要在关闭时额外做的事。
    yield


# app:创建 FastAPI 应用的实例,这是整个程序真正对外提供服务的对象——
# 下面所有 @app.get/@app.post 装饰器,都是往这一个 app 实例上"挂"路由。
app = FastAPI(
    # title/description/version:纯粹是给自动生成的 API 文档(浏览器访问
    # /docs 时看到的那个交互式页面)用的说明性信息,不影响实际接口行为。
    title="Petstore API",
    description="Beginner FastAPI Petstore application. Source of truth for pets, availability, and orders.",
    version="0.1.0",
    # lifespan=lifespan:把上面定义的生命周期函数,注册给这个应用——告诉
    # FastAPI "应用启动的时候,请执行 lifespan 里 yield 之前的那些代码"。
    lifespan=lifespan,
)


# @app.get("/health"):声明"当有人用 HTTP GET 方法访问 /health 这个路径时,
# 调用下面这个函数"——这是最简单的健康检查接口,用来确认服务是否存活。
@app.get("/health")
# 返回类型注解 dict[str, str]:表示这个函数会返回一个"键和值都是字符串的
# 字典"——FastAPI 看到这个类型注解,会自动把返回值序列化成对应的 JSON。
def health() -> dict[str, str]:
    # 直接返回一个写死的字典,前端/调用方看到的就是 {"status": "ok"}。
    return {"status": "ok"}


# @app.get("/pets", response_model=list[schemas.Pet]):声明这是"搜索/列出
# 宠物"的接口。response_model=list[schemas.Pet] 告诉 FastAPI:不管函数内部
# 实际返回的是什么类型的对象,都要先按 schemas.Pet 这个模型的字段"过滤+校验"
# 一遍,再序列化成一个 Pet 对象组成的 JSON 数组返回给调用方——即使函数体
# 返回的其实是数据库行对象(PetRow),也会被转换成规整的、只暴露该暴露字段的
# JSON。
@app.get("/pets", response_model=list[schemas.Pet])
def search_pets(
    # 下面这些参数,由于函数是"路径操作函数"且没有被标成请求体,FastAPI 会
    # 默认把它们当成"URL 查询参数"来解析,比如 /pets?species=dog。
    # species/breed/availability/name_contains:没有额外用 Query(...) 包装,
    # 直接用类型注解 + 默认值 None,表示"可选,不填就是 None"。
    species: Species | None = None,
    breed: str | None = None,
    # min_age_months/max_age_months:用 Query(default=None, ge=0) 显式声明
    # 校验规则——default=None 表示可以不传,ge=0 表示传了必须 >= 0。
    # 这跟 schemas.py 里 Field(ge=0) 的写法是同一套校验语言,只不过 Query
    # 是专门给"URL 查询参数"用的版本。
    min_age_months: int | None = Query(default=None, ge=0),
    max_age_months: int | None = Query(default=None, ge=0),
    # 最低/最高价格,同理,gt=0 表示必须严格大于 0。
    min_price_eur: float | None = Query(default=None, gt=0),
    max_price_eur: float | None = Query(default=None, gt=0),
    availability: Availability | None = None,
    # tags:一个字符串列表类型的查询参数,用 Query(default=None) 声明,
    # 使得 URL 里可以重复出现 ?tags=a&tags=b 这种写法,FastAPI 会自动把它们
    # 收集成一个列表。
    tags: list[str] | None = Query(default=None),
    name_contains: str | None = None,
    # conn: Connection = Depends(get_db):这是"依赖注入"的写法——意思是
    # "这个参数的值,请调用 get_db() 这个函数来生成,而不是从 URL/请求体里解析"。
    # FastAPI 每次处理这个接口的请求时,都会先调用 get_db(),把结果作为
    # conn 传进来——这样每个请求都能拿到一个数据库连接,而这个函数本身完全
    # 不用关心连接是怎么建立、怎么关闭的。
    conn: Connection = Depends(get_db),
# 返回类型注解 list[PetRow]:说明函数体真正返回的是"数据库行对象的列表"
# (还没转换成 schemas.Pet),转换的工作交给上面 response_model 参数自动完成。
) -> list[PetRow]:
    # try/except:把"用收到的这些参数构造一个 PetSearch 对象"这一步包在
    # try 块里——因为 schemas.PetSearch 的校验器(比如上一份文件里那个
    # "价格区间不能反"的规则)如果发现数据不合法,会抛出 ValueError。
    try:
        # 用刚才解析出来的这些查询参数,构造一个 schemas.PetSearch 实例。
        # 这一步会触发 PetSearch 里定义的所有校验器——如果 min_price_eur
        # 大于 max_price_eur,这里就会抛出 ValueError,而不是让不合法的搜索
        # 条件流入下面的数据库查询逻辑。
        search = schemas.PetSearch(
            species=species,
            breed=breed,
            min_age_months=min_age_months,
            max_age_months=max_age_months,
            min_price_eur=min_price_eur,
            max_price_eur=max_price_eur,
            availability=availability,
            tags=tags,
            name_contains=name_contains,
        )
    # 捕获上面可能抛出的 ValueError(具体来说是 Pydantic 校验失败包装出来的
    # 那种)。"as exc" 把这个异常对象绑定到变量 exc,方便下面引用。
    except ValueError as exc:
        # 主动抛出一个 HTTPException:状态码 422(Unprocessable Entity,
        # 意思是"请求格式对,但内容语义不合法"),detail 是把原始异常转成
        # 字符串作为错误信息返回给调用方。
        # "from exc":Python 的"异常链"语法,表示这个新异常是由 exc 直接
        # 引发的,方便调试时看到完整的原始错误来源。
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 校验通过,调用 crud.py 里真正执行数据库查询的函数,把连接和搜索条件
    # 传进去,把查询结果直接返回——这就是这个路由函数唯一的"业务逻辑"部分,
    # 真正的 SQL/查询细节都封装在 crud.list_pets 里。
    return crud.list_pets(conn, search)


# 声明"获取单只宠物详情"的接口:GET /pets/{pet_id}——{pet_id} 是"路径参数"
# 占位符,FastAPI 会自动把 URL 里对应位置的值,按下面函数参数 pet_id: int
# 的类型转换好再传进来(比如访问 /pets/7,pet_id 就会是整数 7)。
# response_model=schemas.Pet:返回值会被转换/校验成单个 Pet 对象的 JSON。
@app.get("/pets/{pet_id}", response_model=schemas.Pet)
def get_pet(pet_id: int, conn: Connection = Depends(get_db)) -> PetRow:
    try:
        # 调用 crud.py 的 get_pet,按 id 查这只宠物。
        return crud.get_pet(conn, pet_id)
    # 捕获 crud 模块里定义的"宠物没找到"这个自定义异常类型
    # (crud.PetNotFoundError,不是 Python 内置异常,是这个项目自己定义的)。
    except crud.PetNotFoundError as exc:
        # 找不到就返回 404(Not Found)状态码,这是"未知宠物 id"场景
        # (Section 13 里的 "unknown pet")在 API 层的真正来源。
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# 声明"创建一只新宠物"的接口:POST /pets。
# pet_in: schemas.PetCreate:因为这个参数*没有*配 Query()/Depends() 之类的
# 标记、又是一个 Pydantic 模型类型,FastAPI 会自动把它理解成"请求体"——也就是
# 调用方需要在 HTTP 请求的 body 里发一段 JSON,FastAPI 自动把它解析、校验成
# 一个 PetCreate 对象(这一步同样会触发 schemas.py 里那一整套宠物字段校验,
# 比如尾巴长度 >= 1 的规则,不满足就自动返回 422,连 try/except 都不用写,
# 因为 FastAPI 框架本身就替你处理了请求体校验失败的情况)。
# status_code=201:声明这个接口成功时返回 HTTP 201(Created),表示
# "资源已创建",而不是默认的 200。
@app.post("/pets", response_model=schemas.Pet, status_code=201)
def create_pet(pet_in: schemas.PetCreate, conn: Connection = Depends(get_db)) -> PetRow:
    # 直接调用 crud.create_pet,把校验通过的宠物数据写入数据库,并返回新建的
    # 那一行记录。
    return crud.create_pet(conn, pet_in)


# 声明"购买宠物"的接口:POST /pets/{pet_id}/purchase。
# 注意这里请求体里没有额外的数据——买哪只宠物完全由 URL 路径里的 pet_id
# 决定,响应模型是 schemas.Order(订单),状态码同样是 201(创建了一笔新订单)。
@app.post("/pets/{pet_id}/purchase", response_model=schemas.Order, status_code=201)
def purchase_pet(pet_id: int, conn: Connection = Depends(get_db)) -> PetRow:
    try:
        # 调用 crud.purchase_pet:真正的"检查库存状态、创建订单、把宠物标记
        # 为已售出"这一整套业务逻辑都在这个函数里(而且很关键的是,这几步必须
        # 是一个不可分割的原子操作,否则会出现"两个人同时买到同一只宠物"的
        # 竞态问题——具体怎么保证见 crud.py 的注释)。
        return crud.purchase_pet(conn, pet_id)
    # 捕获"宠物根本不存在"的情况,返回 404。
    except crud.PetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # 捕获"宠物存在,但当前状态不可购买"(比如已经被别人买走了)的情况,
    # 返回 409(Conflict,表示"请求和资源当前状态冲突")——
    # 这正是"库存变化"("changed availability")和"重复购买"
    # ("repeated purchase")这两个 Section 13 场景在 API 层真正的实现依据:
    # 第二次购买同一只宠物,这里会走到这个分支,而不是意外地再成功一次。
    except crud.PetNotAvailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
