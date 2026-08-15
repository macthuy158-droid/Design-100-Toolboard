# 小飞侠设计100% · 代码边界

目标：继续迭代功能时，不再因为修改后台、权限或用户系统而误改公共首页。

## 1. 应用入口

`app.py` 是唯一应用组装入口。

它负责：

- 使用 `app_v2.py` 的公共首页 UI
- 安装 SQLite 运行时保护
- 初始化数据库结构与迁移
- 挂载 `/account`
- 挂载 `/developer`
- 挂载 `/manage`
- 在挂载新管理员后台前移除 `app_v2.py` 遗留的旧 `/manage*` 路由
- 将开发者 POST 投稿接口替换为流式上传实现

不要在其他文件再次创建第二套总入口。

## 2. 公共页面

`app_v2.py`

当前保留：

- 首页 UI
- 公共 CSS / JS
- 基础工具数据访问函数
- 基础页面渲染
- 一部分历史公共实现，线上会由 `app.py` 组装时替换或屏蔽

规则：

- 不在此文件新增管理员功能。
- 不在此文件新增小飞侠 / 小游侠身份逻辑。
- 修改首页 UI 时单独提交，不和后台功能修改混在一个 commit。

## 3. 会员与核心业务

`community_core.py`

负责：

- 小飞侠 / 小游侠角色
- 密码散列与会员 session
- 工具 owner 权限
- 订单 / entitlement
- 评价
- 投稿数据
- 历史数据迁移与约束

`community_portal.py`

负责：

- 登录 / 注册 / 退出
- 个人中心
- 小飞侠开发者页面
- 产品详情中的购买、评价和下载门禁
- 投稿表单 UI

版本更新必须同时满足：前端只显示 owner 工具、POST 接口再次校验 owner、数据库审核约束三层保护。

## 4. 开发者安装包上传

`developer_upload.py`

负责：

- POST `/developer/submit`
- 登录和小飞侠身份检查
- 原开发者 owner 检查
- 新工具 / 新版本参数校验
- 保存成功后写入 `tool_submissions`

`upload_storage.py`

负责：

- 4MB 分块读取上传文件
- 直接写入磁盘，不把几百 MB 安装包整体读入内存
- 写入过程中同步计算 SHA256
- 限制最大安装包大小
- 空文件、超限、异常时删除 `.part` / 残留文件

上传文件期间不保持 SQLite 写事务。

## 5. 管理后台

`admin_portal.py`

只负责：

- 管理员用户名 + 密码登录
- 管理后台首页
- 工具基础资料
- 工具价格
- 上下架
- 版本历史只读

`community_admin.py`

只负责：

- 投稿审核
- 小飞侠 / 小游侠用户管理
- CAD-100 院内人员导入

管理员不直接上传新工具或新版本。

## 6. 数据库运行保护

`runtime_support.py`

负责：

- SQLite `foreign_keys = ON`
- SQLite `busy_timeout`
- 异常自动 rollback
- `community_core.init_db()` 每个进程只实际执行一次

当前仍使用 SQLite；未来只有在并发量明显增加后再评估 PostgreSQL，不需要提前复杂化。

## 7. 数据与文件

运行数据位于 `TOOLBOARD_DATA_DIR`，默认包括：

- `toolboard.db`
- `packages/`
- `submissions/`

这些目录不得提交到 Git。

## 8. 自动检查

GitHub Actions 会自动执行：

- Python 编译检查
- 路由结构检查
- 管理后台旧路由泄漏检查
- 开发者流式投稿接口检查
- 小飞侠免费下载规则
- 小游侠必须拥有非零 paid entitlement 才能下载
- 原开发者 owner 权限检查
- 流式上传文件一致性 / SHA256 / 超限清理检查

对应脚本：

- `scripts/check_structure.py`
- `scripts/check_business_rules.py`
- `scripts/check_upload_storage.py`

## 9. 修改原则

每次上线尽量保持一种类型的改动：

- UI commit
- 权限 / 业务 commit
- 数据迁移 commit
- 存储 / 上传 commit
- 部署 commit

不要再为了一个后台字段整体替换公共首页文件。

发布前至少运行：

```bash
python -m py_compile app.py app_v2.py admin_portal.py community_core.py community_portal.py community_admin.py runtime_support.py upload_storage.py developer_upload.py main.py
python scripts/check_structure.py
python scripts/check_business_rules.py
python scripts/check_upload_storage.py
```
