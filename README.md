# 小飞侠设计100% · Desgin 100%

面向设计师的工具发布、下载与开发者生态平台。

当前产品分为三类身份：

- **小飞侠**：院内人员，由管理员添加或从 CAD-100 用户库导入；默认具备开发者身份，可提交新工具，并且只能更新自己拥有的工具。
- **小游侠**：同行用户，自助注册；可购买、下载、评价工具，但不能发布工具。
- **管理员**：独立后台账号；负责投稿审核、工具基础资料/价格/上下架和用户管理，不直接上传工具版本。

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

> 微信 / 支付宝真实在线支付尚未接入。当前代码不会伪造支付成功。

## 运行入口

唯一推荐启动入口：

```bash
uvicorn app:app --host 127.0.0.1 --port 8100
```

`main.py` 只是兼容入口，内部同样指向 `app:app`。

## 服务器环境变量

```env
TOOLBOARD_ADMIN_USERNAME=admin
TOOLBOARD_ADMIN_PASSWORD=change-me
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
