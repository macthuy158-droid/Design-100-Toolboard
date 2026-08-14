# 深圳院设计100% · 工具开发板

独立的院内工具发布与下载门户。

## 功能

- 公共工具首页
- 按累计下载量自动排行
- 工具详情页
- 工具版本与更新说明
- 安装包下载与下载量统计
- 密码保护的管理后台
- 后台新增工具与发布版本

## 本地启动

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export TOOLBOARD_ADMIN_PASSWORD='change-me'
export TOOLBOARD_SESSION_SECRET='change-me-to-a-long-random-string'
uvicorn app:app --host 127.0.0.1 --port 8100
```

Windows PowerShell 可使用 `$env:TOOLBOARD_ADMIN_PASSWORD` 和 `$env:TOOLBOARD_SESSION_SECRET` 设置环境变量。

## 目录

- `app.py`：FastAPI 站点与后台
- `requirements.txt`：Python 依赖
- `data/`：运行时数据库与安装包，不提交 Git

## 推荐部署

建议与 CAD-100 授权服务分开运行，例如：

- 工具门户：`tools.viewonly.cloud` → `127.0.0.1:8100`
- CAD-100 授权：`auth.viewonly.cloud` → `127.0.0.1:8000`

两者可以部署在同一台腾讯云服务器，但使用独立目录、独立 systemd 服务、独立数据库。
