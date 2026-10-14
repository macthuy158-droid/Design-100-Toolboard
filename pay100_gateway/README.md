# Pay100 微信支付网关（独立部署）

此目录为支付服务器使用的代码，网站仍使用根目录的 app.py。不要覆盖网站的 app.py。
使用 MIT 许可的第三方 SDK `minibear2021/wechatpayv3==2.0.4`，不是微信官方 Python SDK。
SDK 负责 Native 下单、微信响应验签、通知验签解密及查单；业务代码负责订单绑定、金额校验和授权事件可靠转发。

## 已实现

- 网站签名 `POST /api/checkout`，请求/响应契约兼容根目录 PAYMENTS.md。
- 不可变金额、币种、描述、商户订单号和900秒有效期。同一订单返回已保存二维码。
- 网络超时后保留本地订单；只用同一订单号与有效期重试，不创造新的扣款订单。
- 微信原始通知 `POST /api/wechat/notify`：公钥ID、时间戳、SDK验签解密、商户身份、Native类型、成功状态、已存在订单及应付总金额核对。
- 支付事实与通知 outbox 同事务写入，交易号唯一，重复通知不会重复生成授权事件。
- worker 每5秒扫描 outbox，只在网站返回204后标记送达；失败指数退避，最长1小时，进程重启恢复。
- 未支付订单每60秒查单补偿，查单发现已支付也进入同一 outbox；每轮最多20单。
- 签名 `POST /api/orders/query`，请求为 `{"order_no":"D100..."}`，仅供可信网站/运维调用。

## 部署前准备

本地测试不代表真实微信已接通。需要 Python 3.10+。
服务器当前 `.env` 中的 WECHAT_APP_ID、WECHAT_MCH_ID、WECHAT_API_V3_KEY、WECHAT_CERT_SERIAL、
WECHAT_PRIVATE_KEY_PATH、WECHATPAY_PUBLIC_KEY_PATH、WECHATPAY_PUBLIC_KEY_ID、WECHAT_NOTIFY_URL 全部沿用。
默认配置文件仍为 `C:\pay100-secrets\.env`。
另外在这个配置文件中添加：

```text
PAY100_BRIDGE_SECRET=<生成独立随机密钥，至少32字节>
PAY100_SETTLEMENT_URL=https://<网站实际域名>/api/payments/settled
```

网站配置相同的 PAY100_BRIDGE_SECRET，PAY100_GATEWAY_URL=https://pay100.cloud，
PAY100_CHECKOUT_ENABLED 暂保持0。桥接密钥不能使用 APIv3 密钥或登录会话密钥。
网站实际域名必须由部署环境确认，不能使用文档中的占位域名。
密钥、证书、数据库和日志不要放入本仓库。SDK关闭调试日志，避免记录 Authorization。

## Windows 安装与回滚

1. 确認现有测试订单均已结束。新的回调只接受此网关已登记的 D100 订单，不再按 TEST 前缀自动创建订单。
2. 停止计划任务 `Pay100 FastAPI`，并确认8101端口进程已退出。保留原 run_pay100.cmd。
3. 备份当前 app.py 和 pay100.db。若数据库使用 WAL，还应在停止进程后保留对应 -wal / -shm 文件或使用 SQLite backup API。
4. 仅将本目录 app.py、service.py、requirements.txt 复制到 `C:\wwwroot\pay100`。
5. 在服务器 PowerShell 运行：

```powershell
Set-Location C:\wwwroot\pay100
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\venv\Scripts\python.exe -m py_compile .\app.py .\service.py
```

6. 更新私密配置，启动原计划任务。原启动方式 `uvicorn app:app` 可继续使用。
7. 检查本地及公网 `/health`；这一步只说明服务启动，不证明收款成功。

数据库使用原 `data\pay100.db`，仅增加 gateway_orders / gateway_outbox，保留原 payment_orders。
回滚时恢复旧 app.py 并重新启动原计划任务；不要删除新增表，保留已支付订单和待转发事件以便恢复处理。
不要在真实订单仍未结清时切回仅支持 TEST 的旧服务。

## 联调验收

先在测试网站/仅管理员可访问的0.01元商品启用微信购买；线上正式商品保持关闭。
实际扫码付款需要商户本人操作，本次代码测试没有调用真实商户API，也没有扣款。

验证：网站订单固定1分 → 网关存储D100订单 → 微信生成二维码 → 扫码付款 → 微信回调 →
网关记录PAID及outbox → 网站返回204并自动开通对应工具/课程。再次通知不重复授权。
测试短暂关闭网站后付款，恢复网站后outbox应自动送达；查单与回调顺序不应影响授权次数。
确认数据库、网站权益、微信商户订单三者金额/订单号/交易号一致后，才在正式网站设 PAY100_CHECKOUT_ENABLED=1。

## 当前限制

- 不接受此前手工 TEST 下单脚本生成的未登记订单，历史记录保留。
- 已付款或过期订单不返回可支付二维码，不自动重新下单。安全关单/重新购买的产品流程尚未实现。
- 此版本没有退款API、退款后权益撤销、拒付、账单对账、开发者分账、Stripe信用卡收款。
- worker 为当前单实例、SQLite部署设计。多实例会重复转发事件，网站幂等校验可防重复授权；高流量前需改造任务领取和数据库。

离线验证：`python scripts/check_pay100_gateway.py`。测试使用临时数据库和生成的RSA密钥，不读取真实配置。
