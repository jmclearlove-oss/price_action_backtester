import os
import json
import zipfile
import requests

def load_config(config_path="/home/bydcv/Downloads/price_action_backtester/data/download_config.json"):
    """读取并解析配置文件"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ 找不到配置文件: {config_path}，请先创建它！")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def download_binance_data():
    # 1. 加载配置
    try:
        config = load_config()
        symbols = config.get("symbols", [])
        intervals = config.get("intervals", [])
        months = config.get("months", [])
        output_dir = config.get("output_directory", "./binance_data")
    except Exception as e:
        print(f"❌ 解析配置文件失败: {e}")
        return

    base_url = "https://data.binance.vision/data/futures/um/monthly/klines"
    
    print("=" * 50)
    print("📋 正在根据配置文件初始化下载任务...")
    print(f"🔹 目标币种 ({len(symbols)} 个): {symbols}")
    print(f"🔹 目标周期 ({len(intervals)} 个): {intervals}")
    print(f"🔹 目标时间 ({len(months)} 个月): {months}")
    print("=" * 50)

    # 2. 核心下载与解压三层循环
    for symbol in symbols:
        print(f"\n🔥 正在处理币种: {symbol} --------------------")
        
        for interval in intervals:
            # 建立本地专属存放目录，如 ./binance_data/BTCUSDT/5m/
            save_dir = os.path.join(output_dir, symbol, interval)
            os.makedirs(save_dir, exist_ok=True)
            
            for ym in months:
                file_name = f"{symbol}-{interval}-{ym}.zip"
                download_url = f"{base_url}/{symbol}/{interval}/{file_name}"
                zip_save_path = os.path.join(save_dir, file_name)
                
                print(f"  ⬇️ 正在下载 [{interval}] -> {file_name} ...")
                
                try:
                    response = requests.get(download_url, stream=True, timeout=15)
                    
                    if response.status_code == 200:
                        # 写入临时 ZIP 压缩包
                        with open(zip_save_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=4096):
                                if chunk:
                                    f.write(chunk)
                        
                        # 自动解压
                        with zipfile.ZipFile(zip_save_path, 'r') as zip_ref:
                            zip_ref.extractall(save_dir)
                        
                        # 清理 ZIP 文件，仅保留解压后的纯 CSV
                        os.remove(zip_save_path)
                        print(f"    ✅ 成功生成本地 CSV")
                        
                    elif response.status_code == 404:
                        print(f"    ❌ 未找到该月数据 (404)，跳过。")
                    else:
                        print(f"    ⚠️ 下载失败，HTTP 状态码: {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"    🚨 网络请求异常: {e}")

if __name__ == "__main__":
    download_binance_data()
    print("\n🎉 配置文件中的所有下载任务处理完毕！")