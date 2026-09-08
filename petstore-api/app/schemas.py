# === 这个文件是什么 ===
# 文件路径:petstore-api/app/schemas.py
# 作用:定义"宠物""搜索条件""购买请求""订单"这几种数据的形状和校验规则。
# 这里用的是 Pydantic 这个第三方库——它的核心能力是:你只需要写一个"长得像
# 普通 Python 类"的东西(继承 BaseModel),声明每个字段该是什么类型、满足什么
# 条件,Pydantic 就会在"创建这个对象"的那一刻自动帮你检查数据对不对,不对就
# 直接抛出异常(而不是让脏数据流入后面的业务逻辑)。FastAPI(main.py 里用到)
# 会自动把这些模型转换成请求体/响应体的 JSON 结构和接口文档,所以这个文件其实
# 就是整个 Petstore 的"数据字典 + 业务规则表"。

# 从 pydantic 这个库里导入五个工具:
#   BaseModel      —— 所有数据模型的基类,继承它就能获得自动校验的能力
#   ConfigDict     —— 用来配置一个模型的"行为选项"(比如下面会用到的
#                      from_attributes,让模型可以直接从数据库对象里取值)
#   Field          —— 给字段附加额外规则(最小值、最大值、默认值等),
#                      而不是只声明类型
#   field_validator —— 装饰器,给"某一个具体字段"写自定义校验函数
#   model_validator —— 装饰器,给"整个模型"写自定义校验函数(常用于要同时
#                      看好几个字段才能判断对不对的情况,比如下面的价格区间)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 从本项目自己的 app/models.py 里导入两个"枚举类型"(有限选项的集合):
#   Availability —— 宠物的库存状态,比如 available(在售)/pending(待定)/sold(已售)
#   Species      —— 宠物的物种,比如 dog/cat/rabbit/bird/reptile/other
# 枚举的好处是:字段值只能是这几个选项之一,写错了 Pydantic 会直接报错,
# 不会出现"随手打错一个字符串"导致数据库里出现脏值的情况。
from app.models import Availability, Species


# PetBase:一只宠物"应该长什么样"的公共基础定义。之所以单独抽出一个 Base 类,
# 是因为下面 PetCreate(创建时用)和 Pet(读取/返回时用)的字段几乎完全一样,
# 只是 Pet 多了一个数据库自动生成的 id —— 用继承避免把同一套字段和校验规则写
# 两遍。
class PetBase(BaseModel):
    # name:宠物名字。Field(min_length=2, max_length=50) 表示:这个字符串
    # 长度必须在 2 到 50 个字符之间,不满足就在"造这个对象"的那一刻直接报错。
    name: str = Field(min_length=2, max_length=50)
    # species:物种,类型是上面导入的 Species 枚举——只能是枚举里定义的那几个值。
    species: Species
    # specific_species:当 species 选了 "other"(其他)时,这里用来补充说明
    # 具体是什么物种。类型是 "str | None",意思是"字符串,或者没有值(None)"
    # —— Python 3.10 起支持用竖线 | 写"联合类型",等价于 Optional[str]。
    # "= None" 是默认值:调用方不传这个字段时,自动当作 None。
    specific_species: str | None = None
    # breed:品种,同样是"可以不填"的字符串,默认为空。
    breed: str | None = None
    # age_months:年龄(按月算)。Field(ge=0) 表示 "greater than or equal to 0"
    # ——必须大于等于 0,不允许负数年龄。
    age_months: int = Field(ge=0)
    # weight_kg:体重(公斤)。Field(gt=0) 表示 "greater than 0"——必须严格
    # 大于 0,体重不能是 0 或负数。
    weight_kg: float = Field(gt=0)
    # tail_length_cm:尾巴长度(厘米)。Field(ge=1) ——必须大于等于 1 厘米,
    # 这正是之前反复验证过的"尾巴太短就拒绝"规则的来源:0.5 会被拒绝(422),
    # 恰好 1.0 会被接受(201)。
    tail_length_cm: float = Field(ge=1)
    # description:宠物介绍文字,长度必须在 10 到 500 个字符之间。
    description: str = Field(min_length=10, max_length=500)
    # price_eur:价格(欧元),必须严格大于 0。
    price_eur: float = Field(gt=0)
    # availability:库存状态,类型是 Availability 枚举。
    # "= Availability.available" 是默认值——新建宠物如果不特意指定,默认就是
    # "在售"状态。
    availability: Availability = Availability.available
    # tags:标签列表(比如 "friendly"、"quiet" 这种特征词)。
    # "list[str]" 表示"字符串组成的列表"。
    # Field(default_factory=list) 表示:如果调用方没传这个字段,默认值是一个
    # *新建的*空列表——之所以要用 default_factory 而不是直接写 "= []",是因为
    # 列表是"可变对象",如果直接写默认值 [],Python/Pydantic 里所有没传 tags
    # 的实例会共享同一个列表对象,一改全改;default_factory=list 保证每次都
    # 单独新建一个空列表,互不影响。
    tags: list[str] = Field(default_factory=list)
    # photo_references:照片引用(比如文件名/URL)列表。
    # Field(min_length=1) 表示这个列表至少要有 1 个元素——宠物必须至少有一张照片。
    photo_references: list[str] = Field(min_length=1)

    # ↓↓↓ 下面是几个"自定义校验器",用来处理 Field() 表达不了的复杂规则 ↓↓↓

    # @field_validator(...)：声明"这个函数是给 name/breed/description/
    # specific_species 这几个字段做校验的"。
    # mode="before" 的意思是:这个函数在 Pydantic *还没有*把值转换成最终类型
    # 之前就先跑一遍——这里用来"预处理"原始输入(比如去掉首尾空格),而不是
    # 在类型已经转换好之后再校验。
    @field_validator("name", "breed", "description", "specific_species", mode="before")
    # @classmethod:因为 field_validator 要求校验函数是类方法(第一个参数是
    # cls 类本身,而不是某个具体实例 self)——这是 Pydantic 校验器的固定写法。
    @classmethod
    def strip_whitespace(cls, value: str | None) -> str | None:
        # 如果这个字段本来就没填(是 None),直接原样返回,不做任何处理。
        if value is None:
            return value
        # .strip() 是 Python 字符串自带的方法,去掉字符串开头和结尾的空白字符
        # (空格、换行、制表符等)——比如 "  Tom  " 会变成 "Tom"。
        stripped = value.strip()
        # "stripped or None":这是 Python 里常见的"短路写法"。
        # 如果 stripped 是"真值"(非空字符串),就返回 stripped 本身;
        # 如果 stripped 是"假值"(去空格后变成了空字符串 ""),就返回 None。
        # 效果就是:一个只输入了空格的字段,会被当成"没填"。
        return stripped or None

    # 单独再给 breed(品种)加一条规则:这次不加 mode="before",意味着这个
    # 校验函数在类型已经转换好、且上面 strip_whitespace 已经跑过之后才执行。
    @field_validator("breed")
    @classmethod
    def breed_not_blank(cls, value: str | None) -> str | None:
        # 这里的意思是:如果 value "不是 None"(说明调用方确实传了这个字段),
        # 但它又是"假值"(比如空字符串 ""——理论上经过上面 strip 处理后不会
        # 再出现,但这里是双重保险),就报错拒绝。
        if value is not None and not value:
            # raise ValueError(...):抛出一个 Python 内置的"值错误"异常。
            # Pydantic 会捕获这种异常,转换成结构化的校验错误信息返回给调用方
            # (FastAPI 层面会变成 HTTP 422 状态码 + 具体的错误描述)。
            raise ValueError("Breed may not be blank when provided.")
        return value

    # 给 tags(标签列表)字段做"前置"校验和清洗,mode="before" 同上,在类型
    # 转换之前先处理原始的列表内容。
    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        # seen 是一个字典,用来记录"已经出现过的标签"——
        # 键(key)是标签小写化之后的样子(用于判断是否重复),
        # 值(value)是标签清洗后、保留原始大小写的样子(用于最终返回)。
        # 类型注解 "dict[str, str]" 表示"键和值都是字符串的字典"。
        seen: dict[str, str] = {}
        # for 循环:依次处理传进来的每一个标签字符串。
        for tag in tags:
            # 去掉这个标签首尾的空白字符。
            cleaned = tag.strip()
            # 如果清洗完是空字符串,说明这是个"空白标签",直接报错拒绝——
            # 对应 README 里"标签不能为空"的规则。
            if not cleaned:
                raise ValueError("Tags may not be blank.")
            # .lower() 把字符串转成全小写,用作判断"是否重复"的依据——
            # 这样 "Friendly" 和 "friendly" 会被当成同一个标签。
            key = cleaned.lower()
            # 如果这个小写版本已经在 seen 字典里出现过,说明是重复标签,报错。
            # f"Duplicate tag: {cleaned}" 是 Python 的 f-string 写法,会把
            # cleaned 变量的实际值嵌入到错误信息字符串里。
            if key in seen:
                raise ValueError(f"Duplicate tag: {cleaned}")
            # 记下这个标签:键是小写版本(用于查重),值是清洗后的原始大小写版本。
            seen[key] = cleaned
        # seen.values() 取出字典里所有的"值"(也就是清洗后的标签本身,已经
        # 去重),list(...) 把它转换成列表返回——这就是最终存进 tags 字段的内容。
        return list(seen.values())

    # @model_validator(mode="after"):跟上面几个 field_validator 不同,
    # 这个装饰器是给"整个模型实例"做校验,而且 mode="after" 表示在所有字段都
    # 已经各自校验、类型转换完成*之后*才执行——因为这里要同时看两个字段
    # (species 和 specific_species)之间的关系,单独看一个字段是判断不出来的。
    @model_validator(mode="after")
    # 注意这里的参数是 self(实例本身),不是 cls——因为 mode="after" 校验器
    # 是实例方法,此时对象已经造好了,可以直接用 self.字段名 读取任意字段的值。
    # 返回类型注解 "PetBase"(带引号,因为在类自己的定义内部,类本身还没定义
    # 完,只能先用字符串形式的"前向引用")。
    def species_requires_specific_species(self) -> "PetBase":
        # 如果物种选的是 "other"(其他),但 specific_species 没填(是 None
        # 或者空字符串,not None/"" 都是 True),就报错——
        # 对应"species 为 other 时必须填写 specific_species"这条规则。
        if self.species == Species.other and not self.specific_species:
            raise ValueError("A specific species is required when species is 'other'.")
        # model_validator(mode="after") 要求返回校验通过后的实例本身
        # (通常就是 self,除非你想替换成另一个实例)。
        return self


# PetCreate:创建宠物时使用的模型。它直接继承 PetBase,内容完全一样,
# 这里用 "pass"(空语句,表示"这个类体里什么都不用做")只是为了在类型层面
# 单独起一个名字——语义上区分"这是用来创建的数据"还是"这是数据库里已经存在
# 的宠物"(见下面的 Pet 类),即便目前两者字段完全相同。
class PetCreate(PetBase):
    pass


# Pet:表示数据库里已经存在的、完整的一只宠物,在 PetBase 的基础上多了一个
# 数据库自动生成的主键 id。这是 API 返回给调用方的"宠物"数据结构。
class Pet(PetBase):
    # model_config 是 Pydantic v2 给模型配置行为的标准写法。
    # ConfigDict(from_attributes=True) 的意思是:允许这个模型直接从一个
    # "普通对象的属性"(比如 SQLAlchemy 查出来的数据库行对象,通过 pet.name、
    # pet.species 这种属性访问,而不是字典的 pet["name"])来构造,
    # 而不是只能从字典构造——这样 app/crud.py 从数据库读出来的 ORM 对象,
    # 可以直接被 Pydantic "拍平"转换成这个 Pet 模型,再由 FastAPI 序列化成
    # JSON 返回。
    model_config = ConfigDict(from_attributes=True)

    # id:数据库自动生成的主键,类型是整数。这个字段只有"已经存在于数据库"的
    # 宠物才有,所以放在 Pet 这里而不是 PetBase 里。
    id: int


# PetSearch:表示一次"搜索宠物"请求里可以带的所有筛选条件。
# 注意它不是继承 PetBase——搜索条件跟宠物本身的字段形状不一样(比如这里是
# "最小年龄/最大年龄"两个字段,而不是 PetBase 里单一的 age_months)。
class PetSearch(BaseModel):
    # 下面这些字段全部是 "字段类型 | None = None" 的写法,也就是"可选筛选条件"
    # ——每一个都可以不填,不填就表示"这个维度不筛选"。

    # 按物种筛选(可选)。
    species: Species | None = None
    # 按品种筛选(可选)。
    breed: str | None = None
    # 最小年龄(月),Field(default=None, ge=0):默认不筛选,但如果填了必须
    # >= 0。
    min_age_months: int | None = Field(default=None, ge=0)
    # 最大年龄(月),同上。
    max_age_months: int | None = Field(default=None, ge=0)
    # 最低价格(欧元),Field(default=None, gt=0):默认不筛选,但填了必须 > 0。
    min_price_eur: float | None = Field(default=None, gt=0)
    # 最高价格(欧元),同上。
    max_price_eur: float | None = Field(default=None, gt=0)
    # 按库存状态筛选(可选)——比如只看"在售"的宠物。
    availability: Availability | None = None
    # 按标签筛选(可选),是一个字符串列表或者 None。
    tags: list[str] | None = None
    # 按名字里包含的关键词筛选(可选),比如搜索名字里带 "Tom" 的宠物。
    name_contains: str | None = None

    # 跟上面 PetBase 里的 strip_whitespace 类似,给 name_contains 这个搜索
    # 关键词做"前置"清洗:去掉首尾空格,只输入空格的等价于没填这个筛选条件。
    @field_validator("name_contains", mode="before")
    @classmethod
    def blank_name_is_no_filter(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    # 这就是之前多次核实过的"年龄/价格区间必须合法"的校验器——
    # mode="after":所有字段各自校验完之后,再统一检查"字段之间的关系"。
    @model_validator(mode="after")
    def age_and_price_ranges_are_consistent(self) -> "PetSearch":
        # 用一个多行的布尔表达式(外层用括号包起来,Python 允许在括号内跨行
        # 写条件,不需要在每行末尾加反斜杠续行符)判断三件事同时成立:
        #   1. min_age_months 确实填了(不是 None)
        #   2. max_age_months 确实填了(不是 None)
        #   3. min_age_months 比 max_age_months 还大(区间是"反的",不合理)
        if (
            self.min_age_months is not None
            and self.max_age_months is not None
            and self.min_age_months > self.max_age_months
        ):
            # 三个条件同时成立,说明年龄区间写反了,报错拒绝。
            raise ValueError("Minimum age may not be greater than maximum age.")
        # 同样的逻辑,换成检查价格区间——这正是之前专门验证过的
        # "Invalid price range"(min_price_eur=500 > max_price_eur=100 时,
        # 接口应该返回 422)这条规则真正的实现位置。
        if (
            self.min_price_eur is not None
            and self.max_price_eur is not None
            and self.min_price_eur > self.max_price_eur
        ):
            raise ValueError("Minimum price may not be greater than maximum price.")
        # 两个区间都没问题(或者其中某个区间根本没填),校验通过,返回自身。
        return self


# PurchaseRequest:表示一次"购买宠物"的请求体,只需要一个字段:要买哪只宠物。
class PurchaseRequest(BaseModel):
    # pet_id:要购买的宠物 id。Field(gt=0):必须是正整数——数据库主键从 1
    # 开始,0 或负数肯定是无效 id,提前在这里拦截,不用等到查数据库才发现。
    pet_id: int = Field(gt=0)


# Order:表示一笔已经生成的订单,是购买成功后返回给调用方的数据结构。
class Order(BaseModel):
    # 跟 Pet 类一样,允许直接从数据库 ORM 对象的属性构造这个模型。
    model_config = ConfigDict(from_attributes=True)

    # id:订单自己的主键。
    id: int
    # pet_id:这笔订单买的是哪只宠物(关联回 Pet 的 id)。
    pet_id: int
    # price_eur:成交价格(欧元)——记录下单那一刻的价格快照,即使宠物表里的
    # 价格以后被改动,这笔订单的历史成交价也不会跟着变。
    price_eur: float
