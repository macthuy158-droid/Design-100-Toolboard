# 小飞侠设计100% · 代码边界

目标：继续迭代功能时，不再因为修改后台、权限或用户系统而误改公共首页。

## 1. 应用入口

`app.py` 是唯一应用组装入口。

它负责：

- 使用 `app_v2.py` 的公共首页 UI
- 挂载 `/account`
- 挂载 `/developer`
- 挂载 `/manage`
- 在挂载新管理员后台前移除 `app_v2.py` 遗留的旧 `/manage*` 路由

不要在其他文件再次创建第二套总入口。

## 2. 公共页面

`app_v2.py`

当前保留：

- 首页 UI
- 公共 CSS / JS
- 基础工具数据访问函数
- 基础页面渲染

规则：

- 不在此文件新增管理员功能。
- 不在此文件新增小飞侠 / 小游侠身份逻辑。
- 修改首页 UI 时单独提交，不和后台功能修改混在一个 commit。

## 3. 会员与开发者

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
- 小飞侠开发者中心
- 新工具与新版本投稿
- 产品详情中的购买、评价和下载门禁

原则：版本更新必须同时满足前端只显示 owner 工具、接口校验 owner、数据库审核约束三层保护。

## 4. 管理后台

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

## 5. 数据与文件

当前使用 SQLite。

运行数据位于 `TOOLBOARD_DATA_DIR`，默认包括：

- `toolboard.db`
- `packages/`
- `submissions/`

这些目录不得提交到 Git。

后续数据库迁移应逐步从请求路径中移出，最终仅在应用启动或独立 migration 命令中执行。

大安装包上传后续统一改为流式写盘，不允许把几百 MB 文件整体读入内存。

## 6. 修改原则

每次上线尽量保持一种类型的改动：

- UI commit
- 权限 / 业务 commit
- 数据迁移 commit
- 部署 commit

不要再为了一个后台字段整体替换公共首页文件。

发布前必须运行：

```bash
python -m py_compile app.py app_v2.py admin_portal.py community_core.py community_portal.py community_admin.py main.py
python scripts/check_structure.py
```

其中结构检查确保旧管理员路由不能重新进入线上应用。
