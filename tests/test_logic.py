import os
import sys
import pandas as pd
import pytest

# 將專案根目錄加入路徑以便載入模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data import is_valid_symbol
from signals import StockSignalEngine

def test_is_valid_symbol():
    """測試台股代碼驗證邏輯"""
    assert is_valid_symbol("2330") == True  # 台積電
    assert is_valid_symbol("2330.TW") == True
    assert is_valid_symbol("0050.TW") == True
    assert is_valid_symbol("99999") == False # 無效代碼
    assert is_valid_symbol("ABCD") == False

def test_round_to_tick():
    """測試台股各價格區間的跳動點 (Tick Size) 進位邏輯"""
    engine = StockSignalEngine()
    
    # < 10: tick 0.01
    assert engine.round_to_tick(9.51) == pytest.approx(9.51)
    
    # 10 ~ 50: tick 0.05
    assert engine.round_to_tick(15.22) == pytest.approx(15.20)
    assert engine.round_to_tick(15.23) == pytest.approx(15.25)
    
    # 50 ~ 100: tick 0.1
    assert engine.round_to_tick(80.14) == pytest.approx(80.1)
    assert engine.round_to_tick(80.16) == pytest.approx(80.2)
    
    # 100 ~ 500: tick 0.5
    assert engine.round_to_tick(251.2) == pytest.approx(251.0)
    assert engine.round_to_tick(251.3) == pytest.approx(251.5)
    
    # 500 ~ 1000: tick 1.0
    assert engine.round_to_tick(600.4) == pytest.approx(600.0)
    assert engine.round_to_tick(600.6) == pytest.approx(601.0)
    
    # > 1000: tick 5.0
    assert engine.round_to_tick(1502.0) == pytest.approx(1500.0)
    assert engine.round_to_tick(1503.0) == pytest.approx(1505.0)

def test_get_trend_status_bullish():
    """測試多頭強勢排列: 5MA > 20MA > 60MA"""
    engine = StockSignalEngine()
    last_row = pd.Series({
        "SMA_5": 100,
        "SMA_20": 90,
        "SMA_60": 80
    })
    assert engine._get_trend_status(last_row) == "多頭強勢"

def test_get_trend_status_pullback():
    """測試多頭拉回: 20MA > 60MA 但 5MA < 20MA"""
    engine = StockSignalEngine()
    last_row = pd.Series({
        "SMA_5": 85,
        "SMA_20": 90,
        "SMA_60": 80
    })
    assert engine._get_trend_status(last_row) == "多頭拉回"

def test_get_trend_status_bearish():
    """測試空頭強勢排列: 5MA < 20MA < 60MA"""
    engine = StockSignalEngine()
    last_row = pd.Series({
        "SMA_5": 70,
        "SMA_20": 80,
        "SMA_60": 90
    })
    assert engine._get_trend_status(last_row) == "空頭強勢"

def test_get_trend_status_rebound():
    """測試空頭反彈: 20MA < 60MA 但 5MA > 20MA"""
    engine = StockSignalEngine()
    last_row = pd.Series({
        "SMA_5": 85,
        "SMA_20": 80,
        "SMA_60": 90
    })
    assert engine._get_trend_status(last_row) == "空頭反彈"

def test_get_trend_status_insufficient_data():
    """測試均線資料不足 (包含 NaN 的情況)"""
    engine = StockSignalEngine()
    last_row = pd.Series({
        "SMA_5": 100,
        "SMA_20": None,
        "SMA_60": 80
    })
    assert engine._get_trend_status(last_row) == "資料不足"
