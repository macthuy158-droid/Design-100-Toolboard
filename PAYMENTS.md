# 人民币购买与历史积分存档

## 商品规则

- 工具与课程使用独立现金订单 `purchase_orders`，人民币价格以分保存。商品页直接购买，不需要充值。
- 积分已停用：停止注册/投稿奖励、工具兑换、积分定价和人工增减。原余额和流水作为历史记录保留，不清零、不折现。
- 开发者仅设置人民币售价：0表示免费，正数表示现金购买。积分字段只为历史兼容保留，不能通过旧接口重新启用。
- 原积分专用工具没有确认人民币价格时显示“待定价”，拒绝新购买。已兑换用户继续下载；原开发者或管理员明确设置现金价格后，才转为免费或现金商品。旧待审投稿也遵守该规则。
- 保留已有积分兑换、历史现金工具授权、课程报名及院内小飞侠免费课程权益。
- 网站外部网页工具目前保持免费。仅隐藏一个外链不能防止绕过付费，不能在没有目标应用鉴权对接时出售该外链。
- 开发者现金销售统计与积分收入分开，销售额是未结算的总额，不代表可提现余额。

## 网站实现

- `POST /account/purchases/new/{tool|course}/{id}` 从服务端商品记录取得价格、购买人和商品信息，保存不可变订单快照；重复下单复用未付款订单。
- `GET /account/purchases/{id}` 显示订单、微信支付入口及二维码，并轮询 `GET /account/purchases/{id}/status`。
- `POST /account/purchases/{id}/wechat` 调用 Pay100 下单；`GET /account/purchases/{id}/qr` 在网站服务器生成二维码，避免第三方二维码服务。
- 购买、兑换及开发者定价使用与登录会话绑定的 CSRF token。订单页、二维码及状态只允许订单本人访问。
- `POST /api/payments/settled` 接收 Pay100 服务端签名成功事件，校验渠道、订单金额、币种、事件ID及交易号，在同一数据库事务中写入交易、订单及工具/课程权益。
- 微信支付通知重试与并发通知不会重复授权；一个交易号不能用于多个订单。前端跳转不作为付款依据。
- 所有新积分兑换返回410，不扣积分、不改变现金订单或权益。历史授权独立于新人民币购买。
- 积分悬赏停止新建/重新开放；已有悬赏保留原处理入口，取消退回冻结积分、完成按原约定结算，均不产生人民币收入。历史余额后续处置需另行约定。
- 原 `orders` / `entitlements` 保留作历史记录与人工确认，不迁移或覆盖。新的现金购买走 `purchase_orders` / `purchase_entitlements`。

## 当前接通范围

网站订单、收银台及授权代码已实现并可使用模拟网关联调。**微信网关已部署，1分真实付款、自动授权和下载已由用户验证；海外信用卡未接入。**
Pay100 后端现已放在 `pay100_gateway/`，采用第三方 `wechatpayv3==2.0.4` SDK。见 `pay100_gateway/README.md` 的独立部署说明。网站和网关分开部署，健康检查不能替代支付验收。
新安装默认不打开微信支付。当前线上已完成微信小额联调并启用；新环境必须完成 Pay100 以下契约、微信通知验签解密、商户信息核对、持久化通知转发重试、查单和0.01元真实端到端测试后再启用。

网站环境变量：

```text
PAY100_GATEWAY_URL=https://pay100.cloud
PAY100_CHECKOUT_ENABLED=0
PAY100_BRIDGE_SECRET=<随机且至少32字节；两个服务器相同>
```

桥接密钥禁止复用 APIv3 密钥或 session 密钥，不得提交到 GitHub。商户私钥与APIv3密钥继续保留在 Pay100 服务器。

## Pay100 下单契约（后端已实现，待真实联调）

网站 POST `{PAY100_GATEWAY_URL}/api/checkout`，JSON：

```json
{"order_no":"D100...","amount_minor":9900,"currency":"CNY","description":"工具名称","provider":"wechat"}
```

请求与成功响应均使用以下 HMAC 请求头。服务器只能接受有效签名，并将订单号、金额与币种持久化绑定；同一订单号不同金额必须拒绝，同一订单重复请求必须幂等返回原支付结果。
Native 支付成功响应 JSON：

```json
{"order_no":"D100...","amount_minor":9900,"currency":"CNY","provider":"wechat","code_url":"weixin://...","expires_at":1800000000}
```

`expires_at` 为实际微信支付截止时间对应的 UNIX 秒数。重复下单不能延长过期交易或产生第二笔扣款。
网站不会盲目为过期二维码重新生成新订单；需先查单/关单后实现安全重试流程。

## 通知转发契约

微信原始回调继续为 `https://pay100.cloud/api/wechat/notify`。
Pay100 必须对原始字节验签，核对签名对应的微信公钥ID/证书序列号及时间戳，用 APIv3 密钥解密，核对 appid、mchid、金额、币种、订单号及 SUCCESS 状态。
网站的 HMAC 不代替微信官方验签。

Pay100 将已验证的支付事实持久化到 outbox，再向网站 POST `/api/payments/settled`，直到返回204；失败要重试，不能在成功接收微信通知后丢失授权事件。

通知体必须恰好为以下六项：

```json
{"provider":"wechat","event_id":"provider-event-id","order_no":"D100...","transaction_id":"wechat-transaction-id","amount_minor":9900,"currency":"CNY"}
```

`amount_minor` 为订单总额，CNY单位为分，微信应取 `amount.total` 而不是优惠后的 `payer_total`。

HMAC请求/响应头：

- `X-Pay100-Timestamp`：当前 UNIX 秒数，允许±300秒。
- `X-Pay100-Signature`：`HMAC-SHA256(secret, timestamp + "\n" + 原始请求体)` 的小写十六进制值。

重试使用新的时间戳和签名，事件ID及交易事实保持不变。使用 HTTPS，避免记录密钥或敏感通知。

## 后续海外信用卡

新现金订单已有渠道与币种字段，预留 `stripe` 渠道，但没有启用收款。
选择服务商与商户主体后，对接托管收银台、服务端固定商品币种与价格、官方 webhook 验签和已付款状态判断；不在网站收集卡号。
外币商品价格需另行配置，不将既有人民币订单临时换币或改金额。退款、拒付、授权撤销、对账和开发者结算仍需单独实现。

官方参考：

- https://pay.wechatpay.cn/doc/v3/merchant/4012791882
- https://docs.stripe.com/payments/checkout/fulfill-orders
