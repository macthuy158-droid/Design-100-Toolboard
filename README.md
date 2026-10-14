# 小飞侠设计100% · Desgin 100%

面向设计师的工具发布、下载与开发者生态平台。

账号身份与开发者资格分别管理：

- 默认 `/account/register` 创建普通账号：昵称、邮箱、密码及确认密码，无需选择身份或邀请码。
- `/account/register/internal` 单独处理院内实名/邀请码注册。已有院内账号保留开发者权限及原课程福利。
- 普通账号在个人中心申请开发者资格，管理员审核通过后可发布工具、维护自己的工具；仍按普通用户规则购买付费课程。
- 管理员是统一用户账号上的独立权限标记，从主网站登录，个人中心和导航出现管理控制台；后台仍在 /manage/，不再使用独立登录密码。
- `TOOLBOARD_GUEST_SIGNUP` 默认1；显式设0可暂停公开注册。当前没有邮箱验证/找回密码服务，未声称验证邮箱归属。

## 当前功能

- 公共工具首页与下载排行
- 工具详情、版本、开发者、评价与留言
- 小飞侠 / 小游侠账号体系
- 小飞侠开发者中心
- 新工具投稿与版本更新审核
- 工具原开发者 owner 权限控制
- 小游侠订单与付费授权数据结构
- 管理后台：投稿审核 / 工具管理 / 用户管理
- CAD-100 院内人员导入
- 下载权限与下载日志
- 开发者安装包流式写盘：4MB 分块读取、边写边计算 SHA256、超限/失败自动清理残留文件

> 工具与课程支持人民币订单及付款后授权，积分已停用，历史兑换权益及账本保留。微信 Pay100 网关已部署并完成1分支付与下载授权验证；海外信用卡渠道暂预留。详见 [PAYMENTS.md](PAYMENTS.md)。

## 运行入口

唯一推荐启动入口：

```bash
uvicorn app:app --host 127.0.0.1 --port 8100
```

`main.py` 只是兼容入口，内部同样指向 `app:app`。

## 服务器环境变量

```env
TOOLBOARD_SESSION_SECRET=change-me-to-a-long-random-string
TOOLBOARD_DATA_DIR=/opt/design100-toolboard/data
CAD100_LICENSE_DB=/opt/cad100-license/data/license.db
```

运行时数据、数据库、安装包和 `.env` 均不提交 Git。

## 当前代码职责

- `app.py`：**唯一应用组装入口**；挂载公共站、账号、开发者和管理员模块，并屏蔽历史旧后台路由。
- `app_v2.py`：公共首页 UI 与早期公共基础代码。**不要在这里新增管理员业务。**
- `runtime_support.py`：SQLite 外键、锁等待、异常回滚，以及数据库初始化只执行一次的运行时保护。
- `community_core.py`：用户、角色、订单、授权、评价、投稿、owner 等核心数据和权限逻辑。
- `community_portal.py`：登录注册、个人中心、开发者页面、产品详情、付费/下载门禁。
- `developer_upload.py`：小飞侠投稿 POST 接口与 owner 校验。
- `upload_storage.py`：安装包流式写盘、大小限制、SHA256 和失败清理。
- `admin_portal.py`：管理员登录、后台首页、工具基础管理。
- `community_admin.py`：投稿审核、用户管理。
- `scripts/check_structure.py`：检查重复路由、旧后台泄漏、流式投稿接口是否生效。
- `scripts/check_business_rules.py`：检查小飞侠免费下载、小游侠付费门禁、owner 权限。
- `scripts/check_upload_storage.py`：检查流式保存、SHA256、超限清理。
- `.github/workflows/structure-check.yml`：GitHub 自动编译和上述检查。

更详细的边界见 `ARCHITECTURE.md`。

## 本地启动

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export TOOLBOARD_ADMIN_USERNAME=admin
export TOOLBOARD_ADMIN_PASSWORD=change-me
export TOOLBOARD_SESSION_SECRET=change-me-to-a-long-random-string
uvicorn app:app --host 127.0.0.1 --port 8100
```

## 发布前检查

```bash
python -m py_compile app.py app_v2.py admin_portal.py community_core.py community_portal.py community_admin.py runtime_support.py upload_storage.py developer_upload.py main.py
python scripts/check_structure.py
python scripts/check_business_rules.py
python scripts/check_upload_storage.py
```

GitHub Actions 会在 push / pull request 时自动执行这些检查。

## 部署

当前生产站：

- 小飞侠设计100%：`100.ecomirro.com` → `127.0.0.1:8100`
- CAD-100 授权服务：独立服务与数据库

两个项目保持独立 Git 仓库、独立 systemd 服务和独立运行目录。

## 统一管理员登录与绑定

`is_admin` 与院内身份、开发者资格独立，默认0；注册和开发者审核不能授予管理员权限。
在服务器终端执行 `scripts/grant_admin.py --database <实际toolboard.db路径> --username <准确登录用户名>`，
仅匹配一个已启用的登录用户名，先备份数据库再记录授权，不按昵称猜测，不创建账号，不修改密码或已有购买。
这是服务器CLI，不是公开网站接口。进入后台使用该账号原有主站密码。
旧环境中的 TOOLBOARD_ADMIN_USERNAME/PASSWORD 不再用于登录，旧管理员Cookie与POST /manage/login不再授权。
统一后台POST使用用户会话绑定CSRF，权限撤销/停用即时生效；最后一个启用管理员不能在后台停用。

发布新版本前先成功绑定现有账号，再重启服务；若绑定失败不要重启，以免丢失当前后台入口。
新代码为数据库增加is_admin列与授权审计表，不删除用户或旧业务数据。
# 管理员权限、收入与年度奖金

主管理员通过 `/manage/permissions` 搜索已有登录账号，授予普通管理员、财务查看管理员或主管理员权限；普通管理员不能设置权限或停用管理员。系统阻止撤销或停用最后一个启用的主管理员。所有管理员继续使用主站登录。

现有 `is_admin` 账号升级后保持普通管理员，绝不自动授予财务或主管理员权限。部署时在重启前执行 `sudo python3 scripts/grant_admin.py --database <实际数据库路径> --username "Thuy Mac" --superadmin`，会先备份并只匹配已有登录用户名。

`/manage/revenue` 和 CSV 导出仅主管理员及财务查看管理员可访问，按北京时间付款年度、商品、发布者和币种分别统计已付款及已退款订单。此报表不扣税费和运营成本，不计算个人分成；不新增退款接口或认定知识产权归属。

`/manage/awards` 仅主管理员可操作，按准确用户名建立人民币奖金草稿，核定后由财务实际转账，再填写付款凭证编号登记发放。系统不实际打款、不产生提现余额，已发放记录不能重复发放或取消。财务查看权限不允许核定奖金。

`/manage/audit` 记录权限变更、奖金状态、报表导出及通过身份和CSRF检查的后台写入请求结果；不记录密码或请求体。开发者个人中心没有收入和提现入口。
