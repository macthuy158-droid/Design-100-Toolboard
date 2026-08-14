from app import app
from admin_portal import app as admin_app

# 新版工具后台挂载在 /manage/。
# 保留 app.py 的公开首页、工具详情和下载接口不变。
app.mount("/manage", admin_app)
