# -*- coding: utf-8 -*-
import unittest
import easytrader
import base64


class TestEasytrader(unittest.TestCase):

    def test_login(self):
        # user_str = '3300055265'
        # password_str = '541130'  # bytes.decode(base64.decodebytes(b'123123'))
        user = easytrader.use('gzzq')
        # user.prepare(user='100053072', password=password_str)
        # user = easytrader.use('hb_client')
        # user.prepare(user=user_str, password=password_str)
        user.prepare(config_path="gzzq.json")


if __name__ == '__main__':
    unittest.main()
