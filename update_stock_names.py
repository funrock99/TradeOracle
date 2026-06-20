import pandas as pd
import json
import os

def update_twse_mapping():
    """從本地 dom.txt 同步上市證券代碼對照表 (精確過濾股票版)"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base_dir, "dom.txt")
    output_file = os.path.join(base_dir, "stock_mapping.json")
    
    print(f"正在從 {input_file} 讀取數據並過濾...")
    
    try:
        if not os.path.exists(input_file):
            print(f"錯誤：找不到輸入檔案 {input_file}")
            return False

        # 直接傳遞檔案路徑給 pandas 並指定編碼
        dfs = pd.read_html(input_file, encoding='utf-8')
        df = dfs[0]
        
        # 標題在第一列，並清理欄位名稱的空格
        df.columns = [str(c).strip() for c in df.iloc[0]]
        df = df[1:]
        
        # 載入現有資料以進行對比
        old_mapping = {}
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                old_mapping = json.load(f)
        
        new_mapping = {}
        added_count = 0
        updated_count = 0
        
        # 遍歷每一列進行過濾
        for _, row in df.iterrows():
            raw_val = row.get('有價證券代號及名稱', '')
            industry = str(row.get('產業別', ''))
            
            if isinstance(raw_val, str) and "　" in raw_val:
                parts = raw_val.split("　")
                code = parts[0].strip()
                name = parts[1].strip()
                
                if (code.isdigit() and len(code) == 4 and 
                    industry and industry != "nan" and industry != ""):
                    new_mapping[code] = name
                    
                    # 偵測異動
                    if code not in old_mapping:
                        print(f"  [新增] {code}: {name}")
                        added_count += 1
                    elif old_mapping[code] != name:
                        print(f"  [更名] {code}: {old_mapping[code]} -> {name}")
                        updated_count += 1
        
        # 存儲為 JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(new_mapping, f, ensure_ascii=False, indent=2)
            
        print(f"成功！總計 {len(new_mapping)} 筆股票。異動摘要：新增 {added_count} 筆，更名 {updated_count} 筆。")
        
        # 驗證關鍵樣本
        for test_code in ["2330", "1101", "1605"]:
            if test_code in new_mapping:
                print(f"  [驗證成功] {test_code}: {new_mapping[test_code]}")
        
        return True
    except Exception as e:
        print(f"更新失敗: {e}")
        return False

if __name__ == "__main__":
    update_twse_mapping()
