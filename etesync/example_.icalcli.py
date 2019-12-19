from etesync_interface import EtesyncInterface
import base64

c = {}
# populate c from config file, or from gnome keyring, or from terminal
backend_interface = EtesyncInterface(
    c['email'], c['userPassword'], c['remoteUrl'],
    c['uid'], c['authToken'],
    base64.decodebytes(c['cipher_key'].encode('ascii')))

