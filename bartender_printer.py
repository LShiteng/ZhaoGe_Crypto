import win32com.client
import os
from datetime import datetime

class BartenderPrinter:
    def __init__(self, template_path):
        """
        初始化 BarTender 打印类
        :param template_path: BarTender 模板文件的完整路径
        """
        self.template_path = template_path
        self.bartender = None
        self.format = None
        
    def connect(self):
        """连接到 BarTender"""
        try:
            self.bartender = win32com.client.Dispatch('BarTender.Application')
            self.bartender.Visible = False  # 不显示 BarTender 窗口
            return True
        except Exception as e:
            print(f"连接 BarTender 失败: {str(e)}")
            return False
            
    def open_template(self):
        """打开标签模板"""
        try:
            if not os.path.exists(self.template_path):
                print(f"模板文件不存在: {self.template_path}")
                return False
                
            self.format = self.bartender.Formats.Open(self.template_path)
            return True
        except Exception as e:
            print(f"打开模板失败: {str(e)}")
            return False
            
    def print_label(self, asset_no, device_no, purchase_date, arrival_date, copies=1):
        """
        打印标签
        :param asset_no: 资产编号
        :param device_no: 设备编号
        :param purchase_date: 硬件采购时间
        :param arrival_date: 硬件到厂时间
        :param copies: 打印份数
        """
        try:
            if not self.format:
                print("请先打开模板文件")
                return False
                
            # 设置标签上的值
            self.format.SetNamedSubStringValue("asset_no", str(asset_no))
            self.format.SetNamedSubStringValue("device_no", str(device_no))
            self.format.SetNamedSubStringValue("purchase_date", str(purchase_date))
            self.format.SetNamedSubStringValue("arrival_date", str(arrival_date))
            
            # 打印标签
            self.format.PrintOut(False, False, copies)
            return True
        except Exception as e:
            print(f"打印标签失败: {str(e)}")
            return False
            
    def close(self):
        """关闭连接"""
        try:
            if self.format:
                self.format.Close(0)  # 0 = btDoNotSaveChanges
            if self.bartender:
                self.bartender.Quit(0)  # 0 = btDoNotSaveChanges
        except Exception as e:
            print(f"关闭连接失败: {str(e)}")

def print_asset_label(template_path, asset_info):
    """
    打印资产标签的主函数
    :param template_path: BarTender 模板文件路径
    :param asset_info: 包含标签信息的字典
    """
    printer = BartenderPrinter(template_path)
    
    try:
        if not printer.connect():
            return False
            
        if not printer.open_template():
            return False
            
        success = printer.print_label(
            asset_info['asset_no'],
            asset_info['device_no'],
            asset_info['purchase_date'],
            asset_info['arrival_date'],
            asset_info.get('copies', 1)
        )
        
        return success
    finally:
        printer.close()

def main():
    # BarTender 模板文件路径
    template_path = r"C:\Templates\asset_label.btw"  # 请修改为实际的模板路径
    
    # 测试打印
    asset_info = {
        'asset_no': 'ASSET001',
        'device_no': 'DEV001',
        'purchase_date': datetime.now().strftime('%Y-%m-%d'),
        'arrival_date': datetime.now().strftime('%Y-%m-%d'),
        'copies': 1
    }
    
    if print_asset_label(template_path, asset_info):
        print("打印成功！")
    else:
        print("打印失败！")

if __name__ == "__main__":
    main()
