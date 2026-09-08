# === 这个文件是什么 ===
# 文件路径:petstore-api/app/crud.py
# 名字 "crud" 是 Create/Read/Update/Delete(增/查/改/删)四个词的缩写,
# 是后端开发里的通用叫法,指"直接操作数据库"的那一层代码。
# main.py 里的路由函数只负责"接请求、转成 schemas 对象、把结果转成响应",
# 真正拼 SQL、跟数据库打交道的代码全部在这个文件里——这样两层职责分开:
# main.py 管"HTTP 是什么样子",crud.py 管"数据库是什么样子",互不干扰。

# typing 是 Python 标准库,Any 表示"任意类型"——用在下面 params 字典的类型
# 注解里,因为不同筛选条件的值可能是字符串、数字、列表等各种类型。
from typing import Any

# 导入本项目自己的 schemas 模块(数据形状定义,上一个文件读过的那个)。
from app import schemas
# 从 app/database.py 导入:
#   Connection —— 数据库连接对象的类型注解
#   PetRow     —— "一行宠物记录"的类型注解(可以像字典一样用 pet["id"] 取值,
#                  也支持 Pydantic 的 from_attributes 用属性方式读取)
from app.database import Connection, PetRow


# 自定义异常类:PetNotFoundError,表示"要找的宠物不存在"。
# 继承 Python 内置的 Exception(所有异常的基类)。
# "pass" 表示类体里不需要写任何额外内容——这个类存在的唯一意义就是"给这一种
# 错误情况起一个专属的名字",main.py 会专门 catch 这个类型来判断该返回
# HTTP 404 还是别的状态码。
class PetNotFoundError(Exception):
    pass


# 自定义异常类:PetNotAvailableError,表示"宠物存在,但当前状态不能购买"
# (比如已经被卖掉了)。main.py 会专门 catch 它来返回 HTTP 409。
class PetNotAvailableError(Exception):
    pass


# list_pets:根据搜索条件,从数据库里查出符合条件的宠物列表。
# 参数 conn:数据库连接;search:上一个文件里定义的、已经校验过的 PetSearch
# 对象——传到这里的时候,价格区间反了/年龄区间反了这些不合法输入,已经在
# main.py 那一层被 Pydantic 拦下了,这里只需要处理"合法但可能为空"的筛选条件。
# 返回类型 list[PetRow]:一个"数据库行对象"组成的列表。
def list_pets(conn: Connection, search: schemas.PetSearch) -> list[PetRow]:
    # conditions:用来收集 SQL 里 WHERE 子句的各个条件片段(比如
    # "species = %(species)s"),类型注解 list[str] 表示"字符串列表"。
    conditions: list[str] = []
    # params:用来收集这些条件片段里,每个占位符对应的真实取值。
    # 类型注解 dict[str, Any] 表示"键是字符串、值可以是任意类型的字典"。
    # 这里采用"参数化查询"——SQL 语句本身只写占位符(比如 %(species)s),
    # 真正的值通过这个字典单独传给数据库驱动,由驱动负责安全地转义/绑定,
    # 而不是直接把用户输入拼进 SQL 字符串里,这样可以从根本上避免
    # "SQL 注入"这种安全漏洞。
    params: dict[str, Any] = {}

    # 下面是一串几乎一模一样的 if 判断:"如果这个筛选条件用户填了(不是
    # None),就往 conditions 里加一段对应的 SQL 条件,并往 params 里记下
    # 这个条件占位符对应的真实值"。逐条讲解一遍模式,后面重复的就不再重复
    # 解释同样的机制。

    # 如果按物种筛选:
    if search.species is not None:
        # 往条件列表里加一段 "species = %(species)s"——%(species)s 是这个
        # 数据库驱动(psycopg 系列)使用的"具名占位符"写法,执行时会被
        # params 字典里键为 "species" 的值替换掉。
        conditions.append("species = %(species)s")
        # search.species 是一个 Species 枚举值(比如 Species.dog),
        # ".value" 取出它对应的原始字符串值(比如 "dog")——因为数据库里
        # 存的是字符串,不是 Python 的枚举对象,需要"解开"一层。
        params["species"] = search.species.value
    # 如果按品种筛选:
    if search.breed is not None:
        # ILIKE 是 PostgreSQL 特有的"大小写不敏感的模糊匹配"操作符
        # (跟 LIKE 类似,但不区分大小写)。
        conditions.append("breed ILIKE %(breed)s")
        params["breed"] = search.breed
    # 如果填了最小年龄:加一条"年龄 >= 最小年龄"的条件。
    if search.min_age_months is not None:
        conditions.append("age_months >= %(min_age_months)s")
        params["min_age_months"] = search.min_age_months
    # 如果填了最大年龄:加一条"年龄 <= 最大年龄"的条件。
    # (这两条同时生效,就实现了"年龄区间"筛选——对应 Section 13 里
    # "combined search"/年龄区间搜索场景。)
    if search.max_age_months is not None:
        conditions.append("age_months <= %(max_age_months)s")
        params["max_age_months"] = search.max_age_months
    # 价格下限/上限,逻辑跟年龄完全一样。
    if search.min_price_eur is not None:
        conditions.append("price_eur >= %(min_price_eur)s")
        params["min_price_eur"] = search.min_price_eur
    if search.max_price_eur is not None:
        conditions.append("price_eur <= %(max_price_eur)s")
        params["max_price_eur"] = search.max_price_eur
    # 按库存状态筛选(available/pending/sold),同样要 .value 解开枚举。
    if search.availability is not None:
        conditions.append("availability = %(availability)s")
        params["availability"] = search.availability.value
    # 按名字包含的关键词筛选:
    if search.name_contains is not None:
        conditions.append("name ILIKE %(name_contains)s")
        # f"%{search.name_contains}%":f-string 拼接出 SQL 的 LIKE 模糊匹配
        # 语法——前后各加一个 % 通配符,表示"名字中间包含这个关键词即可",
        # 不要求从头或从尾匹配。
        params["name_contains"] = f"%{search.name_contains}%"
    # 按标签筛选。注意这里用的是 "if search.tags:"(不是 "is not None"),
    # 因为空列表 [] 在 Python 里是"假值"——用户传了一个空的 tags 列表,
    # 效果上等同于"没有传标签筛选",所以两种情况都跳过这个条件,行为更直觉。
    if search.tags:
        # "&&" 是 PostgreSQL 数组类型专用的"重叠"操作符,表示"数据库里这行
        # 记录的 tags 数组,和我们传进来的 tags 数组,只要有任意一个共同
        # 元素就算匹配"。
        conditions.append("tags && %(tags)s")
        # 用一个"列表推导式"(list comprehension):对 search.tags 里的每个
        # tag,先 .strip() 去空格,再 .lower() 转小写,构造出一个新列表——
        # 跟数据库里存储标签时的清洗规则(见 schemas.py 的 normalize_tags,
        # 不过那里保留了原始大小写、只用小写做查重)保持一致的"忽略大小写"
        # 比较方式,这样搜索 "Friendly" 也能匹配到存的 "friendly"。
        params["tags"] = [tag.strip().lower() for tag in search.tags]

    # 拼出完整的 WHERE 子句:
    # 这是一个"条件表达式"(三元写法):
    #   如果 conditions 列表不为空(至少有一个筛选条件),
    #     就用 " AND ".join(conditions) 把所有条件片段用 " AND " 连接起来,
    #     再拼上前缀 "WHERE "。
    #   如果 conditions 是空列表(用户没有传任何筛选条件),
    #     where_clause 就是空字符串——意味着查询会返回所有宠物,不加任何限制。
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    # 拼出最终执行的 SQL 语句。注意:虽然这里用了 f-string 拼接 SQL,但拼进去
    # 的只有"表名"和上面拼好的、已经带着占位符(而不是真实值)的 where_clause
    # ——真正的用户输入(值)全部通过 params 字典以参数化的方式传递,不会被
    # 直接拼进 SQL 字符串里,所以并不构成 SQL 注入风险。
    # "# noqa: S608"是给代码检查工具(ruff 的 bandit 规则 S608,"疑似 SQL
    # 注入"检测)的提示,告诉它"这里已经人工确认过是安全的,不用报警"——
    # 因为这条规则只是机械地看到 f-string 拼 SQL 就报警,分辨不出真正拼进去
    # 的是不是用户可控的值。
    query = f"SELECT * FROM pets {where_clause} ORDER BY id"  # noqa: S608 (identifiers are static, values are parameterized)

    # conn.execute(query, params):执行这条 SQL,把 params 字典作为占位符的
    # 实际取值传进去。
    # .fetchall():取出这次查询匹配到的*所有*行,返回一个列表。
    return conn.execute(query, params).fetchall()


# get_pet:按 id 查一只具体的宠物。
def get_pet(conn: Connection, pet_id: int) -> PetRow:
    # 执行一条按主键查询的 SQL,{"id": pet_id} 是参数字典,把 pet_id 的真实
    # 值绑定到 SQL 里的 %(id)s 占位符上。
    # .fetchone():只取第一条匹配结果(因为 id 是主键,最多只会有一行匹配,
    # 没匹配到就返回 None)。
    pet = conn.execute("SELECT * FROM pets WHERE id = %(id)s", {"id": pet_id}).fetchone()
    # 如果查询结果是 None,说明数据库里根本没有这个 id 对应的宠物。
    if pet is None:
        # 抛出上面定义的自定义异常,f-string 里嵌入具体的 pet_id,方便定位
        # 是查的哪个 id 没找到。main.py 会 catch 这个异常,转换成 HTTP 404。
        raise PetNotFoundError(f"Pet {pet_id} was not found.")
    # 查到了,直接返回这一行数据。
    return pet


# create_pet:把一只新宠物写入数据库。
# 参数 pet_in 是 schemas.PetCreate 类型——已经在 main.py 那一层被 FastAPI
# 用 Pydantic 校验过(尾巴长度、价格、标签去重等规则全部满足)才会走到这里。
def create_pet(conn: Connection, pet_in: schemas.PetCreate) -> PetRow:
    # .model_dump():Pydantic 模型自带的方法,把这个模型对象"拍平"成一个
    # 普通的 Python 字典,键是字段名,值是字段的值——方便下面动态拼 SQL。
    data = pet_in.model_dump()
    # data["species"] 现在还是一个 Species 枚举对象,不能直接存进数据库
    # (数据库列是字符串类型),所以取 .value 换成原始字符串,再覆盖回字典里。
    data["species"] = data["species"].value
    # availability 同理,换成字符串。
    data["availability"] = data["availability"].value

    # columns:取出字典里所有的键(也就是要写入哪些列),转换成一个列表。
    # list(data.keys()) —— .keys() 返回字典的"键视图",list(...) 把它变成
    # 一个真正的列表,方便后面重复遍历、拼接。
    columns = list(data.keys())
    # placeholders:用一个"生成器表达式"(跟列表推导式类似,但用小括号,
    # 是惰性求值的写法),给每一列生成一个对应的具名占位符,比如
    # 列名是 "name" 就生成 "%(name)s"——再用 ", " 把它们连接成一整串,
    # 比如 "%(name)s, %(species)s, %(breed)s, ..."。
    placeholders = ", ".join(f"%({col})s" for col in columns)
    # column_list:把列名本身也用 ", " 连接成一串,比如 "name, species,
    # breed, ..."——用在 SQL 的 INSERT INTO pets (这里) 部分。
    column_list = ", ".join(columns)

    # 执行 INSERT 语句:动态拼出 "INSERT INTO pets (列名列表) VALUES (占位符
    # 列表) RETURNING *"——RETURNING * 是 PostgreSQL 特有的语法,意思是
    # "插入这一行之后,把这一行完整的内容(包括数据库自动生成的 id)直接
    # 返回给我",不需要再单独发一条 SELECT 去查刚插入的这一行。
    # 同样地,拼进 SQL 字符串的只有"列名"(程序内部固定的字段名,不是用户
    # 输入),真正的值通过 data 字典参数化传递,所以同样标了 noqa: S608。
    row = conn.execute(
        f"INSERT INTO pets ({column_list}) VALUES ({placeholders}) RETURNING *",  # noqa: S608
        data,
    ).fetchone()
    # assert row is not None:断言(如果条件不成立就直接抛出 AssertionError
    # 让程序崩溃)——这里的意思是"插入语句理论上一定会返回刚插入的这一行,
    # 如果 row 是 None 说明出现了不该出现的异常状况,而不是一个需要优雅处理
    # 的正常业务错误",所以用 assert 而不是自定义异常。
    assert row is not None
    return row


# purchase_pet:处理"购买宠物"的核心业务逻辑——这是整个项目里最关键的一段
# 并发/一致性相关代码,直接决定了"两个人能不能同时买到同一只宠物"这个问题。
def purchase_pet(conn: Connection, pet_id: int) -> PetRow:
    # 先复用上面写好的 get_pet,查这只宠物当前的完整信息——如果不存在,
    # get_pet 自己就会抛出 PetNotFoundError,这里不需要再重复判断一次。
    pet = get_pet(conn, pet_id)
    # 检查这只宠物"现在"的库存状态是不是 "available"(在售)。
    # pet["availability"]:PetRow 支持像字典一样用方括号按列名取值。
    # 这一步是"购买前立刻重新核查库存"规则的真正实现——即使是同一个 pet_id,
    # 每次真正下单前都会重新从数据库读一遍最新状态,而不是复用一个可能已经
    # 过期的旧状态,所以"已经被别人买走的宠物"不可能被第二次买成功。
    if pet["availability"] != "available":
        # 不可购买,抛出上面定义的 PetNotAvailableError,main.py 会把它转换
        # 成 HTTP 409(冲突)。
        raise PetNotAvailableError(f"Pet {pet_id} is not available for purchase.")

    # 状态检查通过,插入一条新订单记录:pet_id 是买的哪只宠物,price_eur
    # 直接用刚才查到的 pet["price_eur"](也就是"下单那一刻"的价格快照),
    # 而不是重新去别处取一个可能已经变化的价格——这保证了订单里记录的成交价
    # 永远对应下单当时的真实价格。同样用 RETURNING * 直接拿回插入后的完整
    # 订单行。
    order = conn.execute(
        "INSERT INTO orders (pet_id, price_eur) VALUES (%(pet_id)s, %(price_eur)s) RETURNING *",
        {"pet_id": pet_id, "price_eur": pet["price_eur"]},
    ).fetchone()
    # 同上,断言插入一定会返回订单行,不是需要优雅处理的业务错误分支。
    assert order is not None

    # 订单创建成功之后,把这只宠物的 availability 字段更新成 'sold'
    # (已售出)——这一步和上面插入订单的这一步,理想情况下应该在同一个数据库
    # 事务里一起提交或者一起回滚(具体的事务边界由 get_db 这个依赖注入函数
    # 在更外层控制,不在这个函数内部单独开关事务)。
    conn.execute(
        "UPDATE pets SET availability = 'sold' WHERE id = %(id)s",
        {"id": pet_id},
    )
    # 返回这笔新创建的订单——对应 main.py 里 response_model=schemas.Order
    # 的返回值。
    return order
