# 支付接入：网站与 Pay100 的边界

## 当前状态

网站仍使用飞侠币下载工具。现金订单入口是旧逻辑，不应未经产品确认就恢复或将人民币自动兑换为飞侠币。
本次实现的是网站侧结算基础，**尚未接通收银台或真实收款**。微信商户私钥继续保留在 Pay100 服务器，禁止提交到仓库。

网站新增 `POST /api/payments/settled`，仅接收 Pay100 服务端签名的支付成功消息。
默认未配置 `PAY100_BRIDGE_SECRET` 时返回 503；不会开放支付按钮或信任前端“成功”跳转。
海外渠道暂预留 `stripe` 标识，没有部署 Stripe 收款或假定商户开户资格。

## Pay100 对接约定（待在支付后端实现）

1. 网站服务端根据数据库固定订单号、价格、币种和购买用户，调用 Pay100 创建支付。禁止浏览器传入收款金额。
2. 调用前由可信服务端代码执行 `payment_core.bind_order(conn, order_id, 'wechat')`。调用失败或超时需用相同订单号查单/重试，不能切换渠道导致重复扣款。此函数没有公开绑定接口。
3. 微信 Native 返回 code_url，由收银台生成二维码。商户回调仍为 `https://pay100.cloud/api/wechat/notify`。
4. Pay100 对微信通知原始字节验签，检查公钥ID/证书序列号、时间戳，使用 APIv3 密钥解密；核对 appid、mchid、订单号、金额、币种和 SUCCESS 状态。网站的 HMAC 不能替代微信验签。
5. Pay100 在持久化 outbox 保存通知，再向网站发送下面的消息，直到网站返回 204。网站失败时不能丢失事件；只确认接收微信通知而不重试转发会造成付款后未授权。
6. 网站在单个数据库事务中写入支付记录、更新订单、授予工具授权。金额、币种、渠道不符则拒绝；重复通知不会重复授权；一个交易号不能支付两笔订单。

通知原始 UTF-8 JSON（字段必须恰好为以下六项）：

```json
{"provider":"wechat","event_id":"provider-event-id","order_no":"D100...","transaction_id":"wechat-transaction-id","amount_minor":100,"currency":"CNY"}
```

`amount_minor` 是订单总额的最小货币单位整数，CNY 为分。微信应取 `amount.total`，不取优惠后的 `payer_total`。
两个服务器配置相同的随机 `PAY100_BRIDGE_SECRET`（至少32字节），不得复用 APIv3 密钥或用户 session 密钥。

请求头：

- `X-Pay100-Timestamp`：当前 UNIX 秒数，允许 ±300 秒。
- `X-Pay100-Signature`：`HMAC-SHA256(secret, timestamp + "\n" + 原始请求体)` 的小写十六进制值。

重试应使用新的时间戳和签名，保持事件ID及交易事实不变。使用 HTTPS，不记录密钥或完整敏感通知。
GET `/account/orders/{id}/status` 仅向订单本人返回数据库支付状态，供未来收银台轮询。

## 后续必须完成

- 获取现有 Pay100 FastAPI 代码（此仓库没有该代码），核对接口与配置变量后实现下单、查单、验签解密与 outbox。
- 明确首批收费商品：工具直接购买、课程购买或钱包充值。本次只支持已有工具 orders/entitlements；课程和充值应有独立履约逻辑。
- 打通登录用户→固定金额下单→二维码→扫码→回调→自动授权，进行 0.01 元真实测试，并验证重复回调和网络失败重试。
- 再选择海外支付服务商及商户主体。Stripe 等信用卡方案应使用托管收银台、服务端固定币种/价格、官方 webhook 验签、已付款状态判断，并处理退款、拒付及授权撤销。不能用本地汇率临时替换已创建订单金额。

官方参考：
- https://pay.wechatpay.cn/doc/v3/merchant/4012791882
- https://docs.stripe.com/payments/checkout/fulfill-orders
