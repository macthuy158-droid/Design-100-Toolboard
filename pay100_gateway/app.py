"""Copy this folder's contents to C:\\wwwroot\\pay100 only during deployment."""
import os
from pathlib import Path
from dotenv import load_dotenv
from wechatpayv3 import WeChatPay, WeChatPayType
try:
    from .service import Gateway, create_app, https_url
except ImportError:
    from service import Gateway, create_app, https_url

load_dotenv(os.getenv('PAY100_ENV_FILE', r'C:\pay100-secrets\.env'))
e = os.environ
if e['PAY100_BRIDGE_SECRET'] == e['WECHAT_API_V3_KEY']:
    raise ValueError('Bridge secret must differ from the WeChat API v3 key')
notify_url = e['WECHAT_NOTIFY_URL']
if not https_url(notify_url):
    raise ValueError('WECHAT_NOTIFY_URL must use HTTPS')
sdk = WeChatPay(
    wechatpay_type=WeChatPayType.NATIVE, mchid=e['WECHAT_MCH_ID'], appid=e['WECHAT_APP_ID'],
    private_key=Path(e['WECHAT_PRIVATE_KEY_PATH']).read_text(encoding='utf-8'),
    cert_serial_no=e['WECHAT_CERT_SERIAL'], apiv3_key=e['WECHAT_API_V3_KEY'],
    public_key=Path(e['WECHATPAY_PUBLIC_KEY_PATH']).read_text(encoding='utf-8'),
    public_key_id=e['WECHATPAY_PUBLIC_KEY_ID'], notify_url=notify_url,
    timeout=(3, 7), logger=None,
)
gateway = Gateway(
    Path(e.get('PAY100_DATA_DIR', r'C:\wwwroot\pay100\data')) / 'pay100.db', sdk,
    e['WECHAT_APP_ID'], e['WECHAT_MCH_ID'], e['WECHATPAY_PUBLIC_KEY_ID'],
    e['PAY100_BRIDGE_SECRET'], e['PAY100_SETTLEMENT_URL'],
)
app = create_app(gateway)
