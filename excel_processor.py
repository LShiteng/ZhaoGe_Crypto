import os
import pandas as pd
from datetime import datetime
import re
import openpyxl

def extract_first_row_info(text):
    """提取第一行的筛选信息"""
    # 移除可能的空格和特殊字符
    text = text.strip()
    
    # 提取发起时间范围
    date_pattern = r'发起时间：\s*(\d{4}-\d{2}-\d{2})\s*到\s*(\d{4}-\d{2}-\d{2})'
    date_match = re.search(date_pattern, text)
    start_date = date_match.group(1) if date_match else ""
    end_date = date_match.group(2) if date_match else ""
    
    # 提取类型
    type_pattern = r'类型：([^状态]+)'
    type_match = re.search(type_pattern, text)
    type_info = type_match.group(1).strip() if type_match else ""
    
    # 提取状态
    status_pattern = r'状态：([^统计]+)'
    status_match = re.search(status_pattern, text)
    status = status_match.group(1).strip() if status_match else ""
    
    # 提取统计数量
    count_pattern = r'共\s*(\d+)\s*条审批'
    count_match = re.search(count_pattern, text)
    count = count_match.group(1) if count_match else "0"
    
    # 提取备注信息
    note_pattern = r'（[^）]+）'
    note_match = re.search(note_pattern, text)
    note = note_match.group(0) if note_match else ""
    
    return {
        '开始日期': start_date,
        '结束日期': end_date,
        '类型': type_info,
        '状态': status,
        '审批数量': count,
        '备注': note
    }

def extract_approval_count(text):
    """从文本中提取审批数量"""
    pattern = r'共\s*(\d+)\s*条审批'
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0

def process_excel_files(root_dir):
    # 数据表的列
    columns = ['申请编号', '标题', '发起时间', '发起人姓名']
    # 统计表的列
    stat_columns = ['筛选条件', '审批数量']
    
    all_rows = []  # 数据表的行
    stat_rows = []  # 统计表的行
    seen_ids = set()
    total_approvals = 0  # 总审批数

    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                file_path = os.path.join(dirpath, filename)
                try:
                    # 读取A1单元格内容
                    wb = openpyxl.load_workbook(file_path, read_only=True)
                    sheet = wb.active
                    a1_value = sheet['A1'].value
                    if a1_value:
                        a1_text = str(a1_value)
                        approval_count = extract_approval_count(a1_text)
                        total_approvals += approval_count
                        stat_rows.append({
                            '筛选条件': a1_text,
                            '审批数量': approval_count
                        })
                    wb.close()
                    
                    # 读取所有sheet的数据
                    excel_file = pd.ExcelFile(file_path)
                    for sheet_name in excel_file.sheet_names:
                        # 读取数据，跳过第一行
                        df = pd.read_excel(file_path, sheet_name=sheet_name, skiprows=1)
                        
                        # 检查必要列
                        missing_cols = [col for col in columns if col not in df.columns]
                        if missing_cols:
                            print(f"错误：文件 {file_path} 的 {sheet_name} 表缺少必要列：{', '.join(missing_cols)}")
                            continue

                        temp_df = df[columns].copy()
                        temp_df = temp_df[~temp_df['申请编号'].astype(str).str.contains('申请编号')]
                        temp_df = temp_df.dropna(subset=['申请编号'])

                        if temp_df.empty:
                            continue

                        for _, row in temp_df.iterrows():
                            # 检查数据完整性
                            if any(pd.isna(row[col]) for col in columns):
                                continue

                            app_id = str(row['申请编号']).strip()
                            if app_id not in seen_ids:
                                seen_ids.add(app_id)
                                row_data = {}
                                try:
                                    for col in columns:
                                        if col == '发起时间':
                                            row_data[col] = pd.to_datetime(row[col]).strftime('%Y-%m-%d %H:%M')
                                        elif col != '申请编号':
                                            row_data[col] = str(row[col]).strip()
                                        else:
                                            row_data[col] = app_id
                                    all_rows.append(row_data)
                                except Exception as e:
                                    print(f"错误：处理数据时出错：{str(e)}")

                except Exception as e:
                    print(f"错误：处理文件 {file_path} 时出错：{str(e)}")

    if not all_rows:
        print("错误：未找到任何有效数据")
        return None

    # 创建数据表和统计表
    result_df = pd.DataFrame(all_rows, columns=columns)
    stat_df = pd.DataFrame(stat_rows, columns=stat_columns)
    
    # 添加统计总行
    stat_df.loc[len(stat_df)] = ['总计', total_approvals]
    
    # 获取数据总行数
    total_rows = len(result_df)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    try:
        # 保存数据表
        output_file = os.path.join(os.path.dirname(root_dir), f'合并数据_共{total_rows}行_{timestamp}.xlsx')
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # 写入数据表
            result_df.to_excel(writer, index=False, sheet_name='数据表')
            # 写入统计表
            stat_df.to_excel(writer, index=False, sheet_name='统计表')
            
            # 设置数据表格式
            worksheet = writer.sheets['数据表']
            for idx, column in enumerate(worksheet.columns):
                max_length = 0
                column = [cell for cell in column]
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

                if idx == 0:
                    for cell in column[1:]:
                        cell.number_format = '0'
                else:
                    for cell in column[1:]:
                        cell.number_format = '@'
            
            # 设置统计表格式
            worksheet = writer.sheets['统计表']
            for column in worksheet.columns:
                max_length = 0
                column = [cell for cell in column]
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

        print(f"数据已保存到: {output_file}")
        print(f"总共处理了 {total_rows} 行有效数据")
        print(f"所有文件共 {total_approvals} 条审批")
        return output_file
    except Exception as e:
        print(f"错误：保存文件时出错：{str(e)}")
        return None

if __name__ == "__main__":
    root_directory = r"D:\谷歌下载\审核"
    output_file = process_excel_files(root_directory)
