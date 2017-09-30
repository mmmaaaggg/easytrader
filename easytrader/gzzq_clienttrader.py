# coding:utf8
from __future__ import division

import os
import subprocess
from datetime import datetime, timedelta
import tempfile
import time
import traceback
import win32api
import win32gui
from io import StringIO
import re

import math
import pandas as pd
import pyperclip
import win32com.client
import win32con
from PIL import ImageGrab
import pythoncom
from . import helpers
from .log import log
import win32_utils


SHIFT_PRICE = 0.7

class GZZQClientTrader():
    def __init__(self):
        self.Title = ' - 广州总部电信交易1'
        self.re_lpClassName = r'Afx:400000:0:0:.+:0'
        self.lpClassName = None
        # self.base_dir 仅用于在导出持仓信息文件时默认的保存目录
        self.base_dir = r'd:\Downloads'
        self._position_df = None
        self._apply_df = None
        self.ignore_mini_order = 10000

    def prepare(self, config_path=None, user=None, password=None, exe_path='D:\TradeTools\广州证券网上交易\hexin.exe'):
        """
        登陆银河客户端
        :param config_path: 银河登陆配置文件，跟参数登陆方式二选一
        :param user: 银河账号
        :param password: 银河明文密码
        :param exe_path: 银河客户端路径
        :return:
        """
        if config_path is not None:
            account = helpers.file2dict(config_path)
            user = account['user']
            password = account['password']
        self.login(user, password, exe_path)

    def login(self, user, password, exe_path):
        if self._has_main_window():
            self._get_handles()
            log.info('检测到交易客户端已启动，连接完毕')
            return
        if not self._has_login_window():
            if not os.path.exists(exe_path):
                raise FileNotFoundError('在　{} 未找到应用程序，请用 exe_path 指定应用程序目录'.format(exe_path))
            subprocess.Popen(exe_path)
        # 检测登陆窗口
        for _ in range(30):
            if self._has_login_window():
                break
            time.sleep(1)
        else:
            raise Exception('启动客户端失败，无法检测到登陆窗口')
        log.info('成功检测到客户端登陆窗口')

        # 登陆
        self._set_trade_mode()
        self._set_login_name(user)
        self._set_login_password(password)
        for _ in range(10):
            self._set_login_verify_code()
            self._click_login_button()
            time.sleep(3)
            if not self._has_login_window():
                break
            self._click_login_verify_code()

        for _ in range(60):
            if self._has_main_window():
                self._get_handles()
                break
            time.sleep(1)
        else:
            raise Exception('启动交易客户端失败')
        log.info('客户端登陆成功')

    def _set_login_verify_code(self):
        verify_code_image = self._grab_verify_code()
        image_path = tempfile.mktemp() + '.jpg'
        verify_code_image.save(image_path)
        result = helpers.recognize_verify_code(image_path, 'yh_client')
        time.sleep(0.2)
        self._input_login_verify_code(result)
        time.sleep(0.4)

    def _set_trade_mode(self):
        input_hwnd = win32gui.GetDlgItem(self.login_hwnd, 0x4f4d)
        win32gui.SendMessage(input_hwnd, win32con.BM_CLICK, None, None)

    def _set_login_name(self, user):
        time.sleep(0.5)
        input_hwnd = win32gui.GetDlgItem(self.login_hwnd, 0x5523)
        win32gui.SendMessage(input_hwnd, win32con.WM_SETTEXT, None, user)

    def _set_login_password(self, password):
        time.sleep(0.5)
        input_hwnd = win32gui.GetDlgItem(self.login_hwnd, 0x5534)
        win32gui.SendMessage(input_hwnd, win32con.WM_SETTEXT, None, password)

    def _has_login_window(self):
        self.login_hwnd = win32gui.FindWindow(None, self.Title)
        if self.login_hwnd != 0:
            return True
        return False

    def _input_login_verify_code(self, code):
        input_hwnd = win32gui.GetDlgItem(self.login_hwnd, 0x56b9)
        win32gui.SendMessage(input_hwnd, win32con.WM_SETTEXT, None, code)

    def _click_login_verify_code(self):
        input_hwnd = win32gui.GetDlgItem(self.login_hwnd, 0x56ba)
        rect = win32gui.GetWindowRect(input_hwnd)
        self._mouse_click(rect[0] + 5, rect[1] + 5)

    @staticmethod
    def _mouse_click(x, y):
        win32api.SetCursorPos((x, y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)

    def _click_login_button(self):
        time.sleep(1)
        input_hwnd = win32gui.GetDlgItem(self.login_hwnd, 0x1)
        win32gui.SendMessage(input_hwnd, win32con.BM_CLICK, None, None)

    def _has_main_window(self):
        try:
            self._get_handles()
        except:
            return False
        return True

    def _grab_verify_code(self):
        verify_code_hwnd = win32gui.GetDlgItem(self.login_hwnd, 0x56ba)
        self._set_foreground_window(self.login_hwnd)
        time.sleep(1)
        rect = win32gui.GetWindowRect(verify_code_hwnd)
        return ImageGrab.grab(rect)

    @staticmethod
    def _filter_trade_client(pattern, hWnd, hWndList):
        clsname = win32gui.GetClassName(hWnd)
        if re.match(pattern, clsname) is not None:
            hWndList.append((hWnd, clsname))

    def _find_trade_client_hwnd(self):
        trade_client_hWnd = None
        if self.lpClassName is None:
            hwnd_list = []
            win32gui.EnumWindows(lambda hWnd, param:
                                 GZZQClientTrader._filter_trade_client(self.re_lpClassName, hWnd, param),
                                 hwnd_list)
            if len(hwnd_list) > 0:
                trade_client_hWnd, self.lpClassName = hwnd_list[0]
                # self.lpClassName = win32gui.GetClassName(trade_client_hWnd)
        else:
            trade_client_hWnd = win32gui.FindWindow(self.lpClassName, None)  # 交易窗口
        return trade_client_hWnd

    @staticmethod
    def _filter_offer_frame_hwnd(hwnd, hwnd_list):
        x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
        if x2 - x1 == 216 and y2 - y1 == 218:
            hwnd_list.append(hwnd)

    def _find_offer_frame_hwnd(self, entrust_window_hwnd):
        """查找买入、卖出界面五档行情的外层框架hwnd"""
        hWndChildList = []
        win32gui.EnumChildWindows(entrust_window_hwnd, GZZQClientTrader._filter_offer_frame_hwnd, hWndChildList)
        if len(hWndChildList) > 0:
            offer_frame_hwnd = hWndChildList[0]
        else:
            offer_frame_hwnd = None
        return offer_frame_hwnd

    @staticmethod
    def _filter_confirm_win_func(hwnd):
        """ 查找 标题为“提示”的确认框"""
        # 找到classname = '#32770' 的窗体
        re_classname_pattern = '#32770'
        clsname = win32gui.GetClassName(hwnd)
        if re.match(re_classname_pattern, clsname) is None:
            return False
        # 找到 窗体标题为 “提示”的窗体
        hwnd_chld_list = []
        try:
            win32gui.EnumChildWindows(hwnd, lambda hwnd_sub, hwnd_chld_list_tmp: hwnd_chld_list_tmp.append(hwnd_sub),
                                      hwnd_chld_list)
            for hwnd_sub in hwnd_chld_list:
                if win32gui.GetClassName(hwnd_sub) == 'Static' and win32gui.GetWindowText(hwnd_sub) == '提示':
                    return True
        except:
            pass
        return False

    def close_confirm_win_if_exist(self):
        """ 查找 标题为“提示”的确认框"""
        hwnd = win32_utils.find_window_whnd(GZZQClientTrader._filter_confirm_win_func, ret_first=True)
        if hwnd is not None:
            shell = GZZQClientTrader._set_foreground_window(hwnd)
            # Enter 热键 切断
            shell.SendKeys('~')

    def goto_buy_win(self, sub_win=None):
        # 获取委托窗口所有控件句柄
        win32api.PostMessage(self.tree_view_hwnd, win32con.WM_KEYDOWN, win32con.VK_F1, 0)
        time.sleep(0.5)
        if sub_win is None:
            pass
        elif sub_win == 'holding':
            win32api.PostMessage(self.position_list_hwnd, win32con.WM_KEYDOWN, 87, 0)  # 热键 w
        elif sub_win == 'deal':
            win32api.PostMessage(self.position_list_hwnd, win32con.WM_KEYDOWN, 69, 0)  # 热键 e
        elif sub_win == 'apply':
            win32api.PostMessage(self.position_list_hwnd, win32con.WM_KEYDOWN, 82, 0)  # 热键 r
        else:
            log.error('sub_win:%s 无效', sub_win)

    def _get_handles(self):
        # 同花顺有改版，无法依靠窗体名称捕获句柄
        # trade_main_hwnd = win32gui.FindWindow(0, self.Title)  # 交易窗口
        trade_main_hwnd = self._find_trade_client_hwnd()  # 交易窗口
        if trade_main_hwnd is None:
            raise Exception()
        trade_frame_hwnd = win32gui.GetDlgItem(trade_main_hwnd, 0)  # 交易窗口
        operate_frame_hwnd = win32gui.GetDlgItem(trade_frame_hwnd, 59648)  # 操作窗口框架
        operate_frame_afx_hwnd = win32gui.GetDlgItem(operate_frame_hwnd, 59648)  # 操作窗口框架
        hexin_hwnd = win32gui.GetDlgItem(operate_frame_afx_hwnd, 129)
        scroll_hwnd = win32gui.GetDlgItem(hexin_hwnd, 200)  # 左部折叠菜单控件
        self.tree_view_hwnd = win32gui.GetDlgItem(scroll_hwnd, 129)  # 左部折叠菜单控件

        # 获取委托窗口所有控件句柄
        # win32api.PostMessage(self.tree_view_hwnd, win32con.WM_KEYDOWN, win32con.VK_F1, 0)
        # time.sleep(0.5)
        self.goto_buy_win()

        # 买入相关
        entrust_window_hwnd = win32gui.GetDlgItem(operate_frame_hwnd, 59649)  # 委托窗口框架
        self.buy_stock_code_hwnd = win32gui.GetDlgItem(entrust_window_hwnd, 1032)  # 买入代码输入框
        self.buy_price_hwnd = win32gui.GetDlgItem(entrust_window_hwnd, 1033)  # 买入价格输入框
        self.buy_amount_hwnd = win32gui.GetDlgItem(entrust_window_hwnd, 1034)  # 买入数量输入框
        self.buy_btn_hwnd = win32gui.GetDlgItem(entrust_window_hwnd, 1006)  # 买入确认按钮
        self.refresh_entrust_hwnd = win32gui.GetDlgItem(entrust_window_hwnd, 32790)  # 刷新持仓按钮
        entrust_frame_hwnd = win32gui.GetDlgItem(entrust_window_hwnd, 1047)  # 持仓显示框架
        entrust_sub_frame_hwnd = win32gui.GetDlgItem(entrust_frame_hwnd, 200)  # 持仓显示框架
        self.position_list_hwnd = win32gui.GetDlgItem(entrust_sub_frame_hwnd, 1047)  # 持仓列表

        # position_df = self.get_position()
        # log.info(position_df)

        # 获取盘口5档买卖price，盘口买卖vol
        offer_price_frame_hwnd = self._find_offer_frame_hwnd(entrust_window_hwnd)  # 五档行情的外层框架
        # [买一、买二。。。。[价格、vol]]
        offer_buy_5_item_id_list = [[1018, 1014],[1025, 1013],[1026, 1012],[1035, 1015],[1036, 1037]]
        self.offer_buy_5_hwnd_list = [
            [win32gui.GetDlgItem(offer_price_frame_hwnd, price_id), win32gui.GetDlgItem(offer_price_frame_hwnd, vol_id)]
            for price_id, vol_id in offer_buy_5_item_id_list
        ]
        # [卖一、卖二。。。。[价格、vol]]
        offer_sell_5_item_id_list = [[1021, 1016],[1022, 1017],[1023, 1019],[1033, 1034],[1032, 1020]]
        self.offer_sell_5_hwnd_list = [
            [win32gui.GetDlgItem(offer_price_frame_hwnd, price_id), win32gui.GetDlgItem(offer_price_frame_hwnd, vol_id)]
            for price_id, vol_id in offer_sell_5_item_id_list
        ]
        # 仅用于测试买卖盘口函数是否有效
        # offer_buy_list, offer_sell_list = self.get_bs_offer_data()
        # print("offer_buy_list:\n", offer_buy_list)
        # print("offer_sell_list:\n", offer_sell_list)
        win32api.PostMessage(self.tree_view_hwnd, win32con.WM_KEYDOWN, win32con.VK_F2, 0)
        time.sleep(0.5)

        # 卖出相关
        sell_entrust_frame_hwnd = win32gui.GetDlgItem(operate_frame_hwnd, 59649)  # 委托窗口框架
        self.sell_stock_code_hwnd = win32gui.GetDlgItem(sell_entrust_frame_hwnd, 1032)  # 卖出代码输入框
        self.sell_price_hwnd = win32gui.GetDlgItem(sell_entrust_frame_hwnd, 1033)  # 卖出价格输入框
        self.sell_amount_hwnd = win32gui.GetDlgItem(sell_entrust_frame_hwnd, 1034)  # 卖出数量输入框
        self.sell_btn_hwnd = win32gui.GetDlgItem(sell_entrust_frame_hwnd, 1006)  # 卖出确认按钮

        # 撤单窗口
        win32api.PostMessage(self.tree_view_hwnd, win32con.WM_KEYDOWN, win32con.VK_F3, 0)
        time.sleep(0.5)
        cancel_entrust_window_hwnd = win32gui.GetDlgItem(operate_frame_hwnd, 59649)  # 撤单窗口框架
        self.cancel_stock_code_hwnd = win32gui.GetDlgItem(cancel_entrust_window_hwnd, 3348)  # 卖出代码输入框
        self.cancel_query_hwnd = win32gui.GetDlgItem(cancel_entrust_window_hwnd, 3349)  # 查询代码按钮
        self.cancel_buy_hwnd = win32gui.GetDlgItem(cancel_entrust_window_hwnd, 30002)  # 撤买
        self.cancel_sell_hwnd = win32gui.GetDlgItem(cancel_entrust_window_hwnd, 30003)  # 撤卖

        chexin_hwnd = win32gui.GetDlgItem(cancel_entrust_window_hwnd, 1047)
        chexin_sub_hwnd = win32gui.GetDlgItem(chexin_hwnd, 200)
        self.entrust_list_hwnd = win32gui.GetDlgItem(chexin_sub_hwnd, 1047)  # 委托列表

        # 资金股票
        win32api.PostMessage(self.tree_view_hwnd, win32con.WM_KEYDOWN, win32con.VK_F4, 0)
        time.sleep(0.5)
        self.capital_window_hwnd = win32gui.GetDlgItem(operate_frame_hwnd, 0xE901)  # 资金股票窗口框架

    def balance(self):
        return self.get_balance()

    def get_balance(self):
        self._set_foreground_window(self.capital_window_hwnd)
        time.sleep(0.3)
        data = self._read_clipboard()
        return self.project_copy_data(data)[0]

    def buy(self, stock_code, price, amount, **kwargs):
        """
        买入股票
        :param stock_code: 股票代码
        :param price: 买入价格
        :param amount: 买入股数
        :return: bool: 买入信号是否成功发出
        """
        if math.isnan(price):
            log.error("%s, buy price is nan", stock_code)
            return
        amount = str(amount // 100 * 100)
        if math.isnan(price):
            log.error("%s, buy price is nan", stock_code)
            return
        # price = str(price)
        price_str = '%.3f' % price

        try:
            win32gui.SendMessage(self.buy_stock_code_hwnd, win32con.WM_SETTEXT, None, stock_code)  # 输入买入代码
            time.sleep(0.2)
            win32gui.SendMessage(self.buy_price_hwnd, win32con.WM_SETTEXT, None, price_str)  # 输入买入价格
            win32gui.SendMessage(self.buy_amount_hwnd, win32con.WM_SETTEXT, None, amount)  # 输入买入数量
            time.sleep(0.2)
            win32gui.SendMessage(self.buy_btn_hwnd, win32con.BM_CLICK, None, None)  # 买入确定
            log.info("买入：%s 价格：%s 数量：%s", stock_code, price_str, amount)
            time.sleep(0.5)
            # 查找是否存在确认框，如果有，将其关闭
            self.close_confirm_win_if_exist()
        except:
            traceback.print_exc()
            return False
        return True

    def sell(self, stock_code, price, amount, **kwargs):
        """
        卖出股票
        :param stock_code: 股票代码
        :param price: 卖出价格
        :param amount: 卖出股数
        :return: bool 卖出操作是否成功
        """
        if math.isnan(price):
            log.error("%s, sell price is nan", stock_code)
            return
        amount = str(amount // 100 * 100)
        if math.isnan(price):
            log.error("%s, sell price is nan", stock_code)
            return
        # price = str(price)
        price_str = '%.3f' % price

        try:
            win32gui.SendMessage(self.sell_stock_code_hwnd, win32con.WM_SETTEXT, None, stock_code)  # 输入卖出代码
            win32gui.SendMessage(self.sell_price_hwnd, win32con.WM_SETTEXT, None, price_str)  # 输入卖出价格
            win32gui.SendMessage(self.sell_price_hwnd, win32con.BM_CLICK, None, None)  # 输入卖出价格
            time.sleep(0.2)
            win32gui.SendMessage(self.sell_amount_hwnd, win32con.WM_SETTEXT, None, amount)  # 输入卖出数量
            time.sleep(0.2)
            win32gui.SendMessage(self.sell_btn_hwnd, win32con.BM_CLICK, None, None)  # 卖出确定
            log.info("卖出：%s 价格：%s 数量：%s", stock_code, price_str, amount)
            time.sleep(0.5)
            # 查找是否存在确认框，如果有，将其关闭
            self.close_confirm_win_if_exist()
        except:
            traceback.print_exc()
            return False
        return True

    def cancel_entrust(self, stock_code, direction):
        """
        撤单
        :param stock_code: str 股票代码
        :param direction: str 1 撤买， 0 撤卖
        :return: bool 撤单信号是否发出
        """
        # direction = 0 if direction == 'buy' else 1

        try:
            win32gui.SendMessage(self.refresh_entrust_hwnd, win32con.BM_CLICK, None, None)  # 刷新持仓
            time.sleep(0.2)
            win32gui.SendMessage(self.cancel_stock_code_hwnd, win32con.WM_SETTEXT, None, stock_code)  # 输入撤单
            win32gui.SendMessage(self.cancel_query_hwnd, win32con.BM_CLICK, None, None)  # 查询代码
            time.sleep(0.2)
            if direction == 1:
                win32gui.SendMessage(self.cancel_buy_hwnd, win32con.BM_CLICK, None, None)  # 撤买
            elif direction == 0:
                win32gui.SendMessage(self.cancel_sell_hwnd, win32con.BM_CLICK, None, None)  # 撤卖
            time.sleep(0.5)
            # 查找是否存在确认框，如果有，将其关闭
            self.close_confirm_win_if_exist()
        except:
            traceback.print_exc()
            return False
        return True

    @property
    def position(self):
        return self.get_position()

    def get_position(self):
        """
        获取当前持仓信息
        :return: 
        """
        position_df = self._get_csv_data(sub_win_from='deal', sub_win_to='holding')
        if position_df is not None:
            self._position_df = position_df
        return self._position_df

    def get_apply(self):
        """
        获取全部委托单信息
        :return: 
        """
        apply_df = self._get_csv_data(sub_win_from='holding', sub_win_to='apply')
        if apply_df is not None:
            self._apply_df = apply_df
        return self._apply_df

    def _get_csv_data(self, sub_win_from, sub_win_to, fast_mode=False):
        """
        获取全部委托单信息
        :param sub_win_from: 
        :param sub_win_to: 
        :param fast_mode: 默认为 False， 为True时，将不进行窗口切换，只有在确认无需进行窗口切换的情况下才能开启次项 
        :return: 
        """
        file_name = 'table.xls'
        file_path = os.path.join(self.base_dir, file_name)
        # 如果文件存在，将其删除
        if os.path.exists(file_path):
            os.remove(file_path)
        win32gui.SendMessage(self.refresh_entrust_hwnd, win32con.BM_CLICK, None, None)  # 刷新持仓
        time.sleep(0.1)
        # 多次尝试获取仓位
        # fast_mode = True
        for try_count in range(3):
            if not fast_mode:
                self.goto_buy_win(sub_win=sub_win_from)
                time.sleep(0.5)
                self.goto_buy_win(sub_win=sub_win_to)
                time.sleep(0.5)
                win32gui.SendMessage(self.refresh_entrust_hwnd, win32con.BM_CLICK, None, None)  # 刷新持仓
                time.sleep(0.2)
            shell = GZZQClientTrader._set_foreground_window(self.position_list_hwnd)

            # Ctrl +s 热键保存
            shell.SendKeys('^s')
            # 停顿时间太短可能导致窗口还没打开，或者及时窗口打开，但最终保存的文件大小为0
            time.sleep(1)
            # Enter 热键 切断
            shell.SendKeys('~')
            time.sleep(0.2)
            for try_count_sub in range(3):
                if not os.path.exists(file_path):
                    log.warning('文件：%s 没有找到，重按 Enter 尝试', file_path)
                    shell.SendKeys('~')
                    time.sleep(0.2)
                else:
                    break
            # 检查文件是否ok
            if os.path.exists(file_path):
                if os.path.getsize(file_path) > 0:
                    break
                else:
                    os.remove(file_path)

            # 如果第一次尝试生成文件失败，则开始取消 fast_mode
            log.warning('文件：%s 没有找到，取消fast_mode模式，重按尝试', file_path)
            fast_mode = False

        data_df = GZZQClientTrader.read_position_csv(file_path)
        return data_df

    @staticmethod
    def read_position_csv(file_path):
        """读取持仓数据文件，并备份"""
        # file_name = 'table.xls'
        # file_path = os.path.join(self.base_dir, file_name)
        data_df = None
        if os.path.exists(file_path):
            if os.path.getsize(file_path) > 0:
                data_df = pd.read_csv(file_path, sep='\t', encoding='gbk', index_col=0)
                data_df.rename(columns={'证券代码': 'stock_code',
                                        '证券名称': 'sec_name',
                                        '股票余额': 'holding_position',
                                        '可用余额': 'sellable_position',
                                        '参考盈亏': 'profit',
                                        '盈亏比例(%)': 'profit_rate',
                                        '参考成本价': 'cost_price',
                                        '成本金额': 'cost_tot',
                                        '市价': 'market_price',
                                        '市值': 'market_value'}, inplace=True)
            GZZQClientTrader.back_file(file_path)
        else:
            data_df = None
        return data_df

    @staticmethod
    def back_file(file_path):
        if os.path.exists(file_path):
            base_name, extension = os.path.splitext(file_path)
            new_file_name = base_name + datetime.now().strftime('%Y-%m-%d %H_%M_%S') + extension
            os.rename(file_path, os.path.join(base_name, new_file_name))

    @staticmethod
    def project_copy_data(copy_data):
        reader = StringIO(copy_data)
        df = pd.read_csv(reader, sep='\t')
        return df.to_dict('records')

    def _read_clipboard(self):
        for _ in range(15):
            try:
                win32api.keybd_event(17, 0, 0, 0)
                win32api.keybd_event(67, 0, 0, 0)
                win32api.keybd_event(67, 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(17, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.2)
                return pyperclip.paste()
            except Exception as e:
                log.error('open clipboard failed: {}, retry...'.format(e))
                time.sleep(1)
        else:
            raise Exception('read clipbord failed')

    @staticmethod
    def _project_position_str(raw):
        reader = StringIO(raw)
        df = pd.read_csv(reader, sep = '\t')
        return df

    @staticmethod
    def _set_foreground_window(hwnd):
        import pythoncom
        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch('WScript.Shell')
        shell.SendKeys('%')
        win32gui.SetForegroundWindow(hwnd)
        return shell

    @property
    def entrust(self):
        return self.get_entrust()

    def get_entrust(self):
        win32gui.SendMessage(self.refresh_entrust_hwnd, win32con.BM_CLICK, None, None)  # 刷新持仓
        time.sleep(0.2)
        self._set_foreground_window(self.entrust_list_hwnd)
        time.sleep(0.2)
        data = self._read_clipboard()
        return self.project_copy_data(data)

    def get_bs_offer_data(self, stock_code):
        win32gui.SendMessage(self.buy_stock_code_hwnd, win32con.WM_SETTEXT, None, stock_code)  # 输入买入代码
        win32gui.SendMessage(self.refresh_entrust_hwnd, win32con.BM_CLICK, None, None)  # 刷新持仓
        time.sleep(0.5)
        max_try_count = 3
        for try_count in range(max_try_count):
            offer_buy_list = [[helpers.get_text_by_hwnd(hwnd_price, cast=float),
                               helpers.get_text_by_hwnd(hwnd_vol, cast=float)]
                              for hwnd_price, hwnd_vol in self.offer_buy_5_hwnd_list]
            offer_sell_list = [[helpers.get_text_by_hwnd(hwnd_price, cast=float),
                                helpers.get_text_by_hwnd(hwnd_vol, cast=float)]
                              for hwnd_price, hwnd_vol in self.offer_sell_5_hwnd_list]
            if not math.isnan(offer_buy_list[0][0]):
                break
            else:
                time.sleep(0.3)
        else:
            log.error('get_bs_offer_data(%s) has no bs offer data' % stock_code)
        return offer_buy_list, offer_sell_list

    def auto_order(self, stock_target_df, config):
        """
        对每一只股票使用对应的算法交易
        :param stock_target_df: 每一行一只股票，列信息分别为 stock_code(index), final_position, price, wap_mode[对应不同算法名称]
        :param config: {'timedelta_tot': 120, 'datetime_start': datetime.now(), 'interval': 10}
        :return: 
        """
        # rename stock_target_df column name
        if stock_target_df.shape[1] != 3:
            raise ValueError('stock_target_df.shape[1] should be 3 but %d' % stock_target_df.shape[1] )
        stock_target_df.rename(columns={k1: k2 for k1, k2 in
                                        zip(stock_target_df.columns, ['final_position', 'price', 'wap_mode'])})
        # stock_code, init_position, final_position, target_price, direction, wap_mode[对应不同算法名称]
        interval = config.setdefault('interval', 20)
        datetime_start = config.setdefault('datetime_start', datetime.now())

        if 'timedelta_tot' in config:
            datetime_end = datetime.now() + timedelta(seconds=config['timedelta_tot'])
            config['datetime_end'] = datetime_end
        elif 'datetime_end' in config:
            datetime_end = config['datetime_end']
        else:
            raise ValueError("'datetime_end' or 'timedelta_tot' 至少有一个需要在config中配置")

        stock_bs_df = self.reform_order(stock_target_df)
        stock_bs_df.sort_values(by='direction', inplace=True)
        # 跳转到买入窗口
        self.goto_buy_win()
        # 开始循环执行算法交易
        while datetime.now() < datetime_end:
            # 每个股票执行独立的算法交易
            for idx in stock_bs_df.index:
                bs_s = stock_bs_df.ix[idx]
                wap_mode = bs_s.wap_mode
                if wap_mode == 'twap':
                    self.twap_order(bs_s, config)
                else:
                    raise ValueError('%s) %s wap_mode %s error' % (idx, bs_s.stock_code, bs_s.wap_mod))
            # 休息 继续
            time.sleep(interval)

        # 循环结束，再次执行一遍确认所有单子都已经下出去了，价格主动成交
        for idx in stock_bs_df.index:
            bs_s = stock_bs_df.ix[idx]
            wap_mode = bs_s.wap_mode
            if wap_mode == 'twap':
                self.deal_order_active(bs_s)
            else:
                raise ValueError('%s) %s wap_mode %s error' % (idx, bs_s.stock_code, bs_s.wap_mod))


    def reform_order(self, stock_target_df):
        """
        根据持仓及目标仓位进行合并，生成新的 df：
        stock_code(index), init_position, final_position, target_price, direction, wap_mode[对应不同算法名称]
        :param stock_target_df: 
        :return: 
        """
        position_df = self.position
        # position_df['wap_mode'] = 'twap'
        stock_bs_df = pd.merge(position_df, stock_target_df, left_index=True, right_index=True, how='outer').fillna(0)
        stock_bs_df.rename(columns={'holding_position': 'init_position'}, inplace=True)
        stock_bs_df['direction'] = (stock_bs_df.init_position < stock_bs_df.final_position).apply(lambda x: 1 if x else 0)
        stock_bs_df['wap_mode'] = stock_bs_df['wap_mode'].apply(lambda x: 'twap' if x == 0 else x)
        # 如果 refprice == 0，则以 market_price 为准
        for stock_code in stock_bs_df.index:
            if stock_bs_df['ref_price'][stock_code] == 0 and stock_bs_df['market_price'][stock_code] != 0:
                log.info('%06d ref_price --> market_price %f', stock_code, stock_bs_df['market_price'][stock_code])
                stock_bs_df['ref_price'][stock_code] = stock_bs_df['market_price'][stock_code]
        return stock_bs_df

    def calc_order(self, stock_code, ref_price, direction, target_position, position_limit=None):
        """
        计算买卖股票的 order_vol, price
        :param stock_code: 
        :param ref_price: 盘口确实价格时，将使用默认价格
        :param direction: 
        :param target_position: 
        :param position_limit:  对于买入来说，最大持有仓位，对于卖出来说，最低持有仓位
        :return: 
        """
        stock_code_str = '%06d' % stock_code
        order_vol, price = 0, 0
        position_df = self.position
        if stock_code in position_df.index:
            # 如果股票存在持仓，轧差后下单手数
            holding_position = position_df.ix[stock_code].holding_position
            order_vol_target = target_position - holding_position
            order_limit = None if position_limit is None else abs(math.floor(position_limit - holding_position))
        else:
            # 如果股票没有持仓，直接目标仓位
            order_vol_target = target_position
            order_limit = abs(math.floor(position_limit))
        # 若 买入 仓位为负，取消；若卖出，仓位为正，取消 —— 不支持融资融券，防止出现日内的仓位震荡
        if direction == 1 and order_vol_target <= 0:
            return order_vol, price
        elif direction == 0 and order_vol_target >= 0:
            return order_vol, price
        if order_vol_target > 0:
            order_vol_target = math.ceil(order_vol_target / 100) * 100
        else:
            order_vol_target = abs(math.floor(order_vol_target / 100) * 100)

        # 获取盘口价格
        offer_buy_list, offer_sell_list = self.get_bs_offer_data(stock_code_str)
        # 手续费 万2.5的情况下，最低5元，因此最少每单价格在2W以上
        if direction == 1:
            price = offer_sell_list[0][0]
            if math.isnan(price) or price == 0.0:
                price = ref_price
            order_vol_min = math.ceil(20000 / price / 100) * 100
        else:
            price = offer_buy_list[0][0]
            if math.isnan(price) or price == 0.0:
                price = ref_price
            order_vol_min = math.ceil(20000 / price)

        # 计算最适合的下单数量
        if order_limit is None:
            order_vol = order_vol_target
        elif order_limit < order_vol_min:
            order_vol = order_limit
        elif order_vol_target < order_vol_min < order_limit:
            order_vol = order_vol_min
        else:
            order_vol = order_vol_target
        return order_vol, price

    def twap_order(self, bs_s, config):
        """
        简单twap算法交易
        :param bs_s: 
        :param config: {'timedelta_tot': 120, 'datetime_start': datetime.now(), 'interval': 10}
        :return: 
        """
        datetime_now = datetime.now()
        timedelta_consume = datetime_now - config['datetime_start']
        order_rate = timedelta_consume.seconds / config['timedelta_tot']
        if order_rate > 1:
            order_rate = 1
        stock_code = bs_s.name
        stock_code_str = '%06d' % stock_code
        final_position = bs_s.final_position
        init_position = bs_s.init_position
        direction = 1 if init_position < final_position else 0
        if init_position == final_position:
            return
        # 将小额买入卖出过滤掉，除了清仓指令
        ref_price = bs_s.ref_price
        gap_position = final_position - init_position
        if gap_position * ref_price < self.ignore_mini_order and not (direction == 0 and final_position == 0):
            log.info('%s %s %d -> %d 参考价格：%f 单子太小，忽略',
                     stock_code_str, '买入' if direction == 1 else '卖出', init_position, final_position, ref_price)
            return
        target_position = init_position + gap_position * order_rate
        self.cancel_entrust(stock_code_str, bs_s.direction)
        order_vol, price = self.calc_order(stock_code,
                                           ref_price=ref_price,
                                           direction=direction,
                                           target_position=target_position,
                                           position_limit=final_position)
        if math.isnan(order_vol) or order_vol <= 0 or math.isnan(price) or price <= 0:
            return
        # 执行买卖逻辑
        if direction == 1:
            price = price - SHIFT_PRICE  # 测试用价格，调整一下防止真成交了
            log.debug('算法买入 %s 卖1委托价格 %f', stock_code_str, price)
            self.buy(stock_code_str, price, order_vol)
        else:
            price = price + SHIFT_PRICE  # 测试用价格，调整一下防止真成交了
            log.debug('算法卖出 %s 买1委托价格 %f', stock_code_str, price)
            self.sell(stock_code_str, price, order_vol)

    def deal_order_active(self, bs_s):
        # 主动成交
        stock_code = bs_s.name
        stock_code_str = '%06d' % stock_code
        final_position = bs_s.final_position
        init_position = bs_s.init_position
        # 将小额买入卖出过滤掉，除了清仓指令
        ref_price = bs_s.ref_price
        gap_position = final_position - init_position
        direction = 1 if init_position < final_position else 0
        if gap_position * ref_price < self.ignore_mini_order and not (direction == 0 and final_position == 0):
            log.info('%s %s %d -> %d 参考价格：%f 单子太小，忽略',
                     stock_code_str, '买入' if direction == 1 else '卖出', init_position, final_position, ref_price)
            return
        self.cancel_entrust(stock_code, bs_s.direction)
        position_df = self.position
        if stock_code in position_df.index:
            order_vol = final_position - position_df.ix[stock_code].holding_position
        else:
            order_vol = final_position
        direction = 1 if order_vol > 0 else 0
        offer_buy_list, offer_sell_list = self.get_bs_offer_data(stock_code_str)
        # 主动成交选择买卖五档价格中的二挡买卖价格进行填报
        if direction == 1:
            price = offer_sell_list[1][0]
            price = ref_price if math.isnan(price) else price
            price = price - SHIFT_PRICE  # 测试用价格，调整一下防止真成交
            log.debug('主动买入 %s卖2委托价格 %f', stock_code_str, price)
            self.buy(stock_code_str, price, order_vol)
        else:
            price = offer_buy_list[1][0]
            price = ref_price if math.isnan(price) else price
            price = price + SHIFT_PRICE  # 测试用价格，调整一下防止真成交
            log.debug('主动卖出 %s买2委托价格 %f', stock_code_str, price)
            self.sell(stock_code_str, price, abs(order_vol))