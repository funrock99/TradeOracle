<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { Search, Activity, AlertTriangle, TrendingUp, BarChart2 } from 'lucide-vue-next'

const symbol = ref('')
const loading = ref(false)
const error = ref(null)
const data = ref(null)

const searchStock = async () => {
  if (!symbol.value) return
  
  loading.value = true
  error.value = null
  data.value = null
  
  try {
    const response = await axios.get(`http://127.0.0.1:5000/api/analyze?symbol=${symbol.value}`)
    if (response.data.success) {
      data.value = response.data.data
    } else {
      error.value = response.data.error
    }
  } catch (err) {
    error.value = err.response?.data?.error || err.message
  } finally {
    loading.value = false
  }
}

const formatNumber = (num, decimals = 2) => {
  if (num === null || num === undefined) return '---'
  return Number(num).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

const getChangeColor = (change) => {
  if (!change) return ''
  return change > 0 ? 'text-red' : change < 0 ? 'text-green' : ''
}
</script>

<template>
  <div class="app-container">
    <header class="glass-panel header">
      <div class="logo">
        <Activity class="icon-accent" />
        <h1>TradeOracle <span class="badge">PRO</span></h1>
      </div>
      <div class="search-bar">
        <input 
          v-model="symbol" 
          @keyup.enter="searchStock"
          type="text" 
          placeholder="輸入台股代碼 (如: 2330)" 
        />
        <button @click="searchStock" :disabled="loading" class="search-btn">
          <Search v-if="!loading" size="18" />
          <span v-else class="loader"></span>
        </button>
      </div>
      <div v-if="data && data.report_url" class="header-actions">
        <a :href="data.report_url" target="_blank" class="report-btn">
          開啟互動報告 (Plotly)
        </a>
      </div>
    </header>

    <main class="content">
      <div v-if="error" class="glass-panel error-card animate-fade-in">
        <AlertTriangle size="24" />
        <p>{{ error }}</p>
      </div>

      <div v-if="!data && !loading && !error" class="empty-state animate-fade-in">
        <BarChart2 size="64" class="empty-icon" />
        <h2>準備好探索市場了嗎？</h2>
        <p>請在上方輸入台股代碼以獲取專家級分析報告。</p>
      </div>

      <div v-if="data" class="dashboard animate-fade-in">
        <!-- 行情摘要 -->
        <section class="glass-panel card market-card">
          <div class="card-header">
            <h3>行情摘要</h3>
            <span class="date">{{ data.last_date.replace(/-/g, '/') }}</span>
          </div>
          <div class="stock-info">
            <h2 class="stock-name">{{ data.stock_name }} <span>({{ data.symbol }})</span></h2>
            <div class="price-row">
              <span class="price">{{ formatNumber(data.close) }}</span>
              <span class="change" :class="getChangeColor(data.change)">
                {{ data.change > 0 ? '▲' : '▼' }} {{ Math.abs(data.change).toFixed(2) }} 
                ({{ data.pct_change > 0 ? '+' : '' }}{{ formatNumber(data.pct_change) }}%)
              </span>
            </div>
            <p class="subtitle">{{ data.is_intraday ? '盤中最新價' : '收盤價' }}</p>
            <div class="volume-info">
              <p>成交量: {{ formatNumber(data.volume / 1000, 0) }} 張</p>
              <p>5日均量: {{ data.vma5 ? formatNumber(data.vma5 / 1000, 0) : '---' }} 張</p>
            </div>
          </div>
        </section>

        <!-- 專家決策 -->
        <section class="glass-panel card verdict-card">
          <div class="card-header">
            <h3>專家決策</h3>
          </div>
          <div class="verdict-box" :class="'bg-' + data.advice_color">
            <p class="verdict-text">{{ data.advice_text }}</p>
          </div>
          <div class="key-levels">
            <div class="level-item">
              <span class="label">壓力位</span>
              <span class="value">{{ formatNumber(data.resistance) }}</span>
            </div>
            <div class="level-item">
              <span class="label">支撐位</span>
              <span class="value">{{ formatNumber(data.support) }}</span>
            </div>
            <div class="level-item stop-loss">
              <span class="label">停損位</span>
              <span class="value">{{ formatNumber(data.stop_loss) }}</span>
            </div>
          </div>
        </section>

        <!-- 技術指標 -->
        <section class="glass-panel card metrics-card">
          <div class="card-header">
            <h3>技術指標矩陣</h3>
          </div>
          <table class="metrics-table">
            <thead>
              <tr>
                <th>指標名稱</th>
                <th>當前數值</th>
                <th>狀態判定</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>均線排列 (5/20/60)</td>
                <td>SMA</td>
                <td :class="data.trend_status.includes('多') ? 'text-red' : data.trend_status.includes('空') ? 'text-green' : 'text-yellow'">
                  {{ data.trend_status }}
                </td>
              </tr>
              <tr>
                <td>RSI (14)</td>
                <td>{{ formatNumber(data.rsi14, 1) }}</td>
                <td :class="data.rsi14 > 70 ? 'text-red' : data.rsi14 < 30 ? 'text-green' : 'text-blue'">
                  {{ data.rsi14 > 70 ? '超買' : data.rsi14 < 30 ? '超賣' : '中性' }}
                </td>
              </tr>
              <tr>
                <td>K/D 指標</td>
                <td>{{ formatNumber(data.kd_k, 1) }} / {{ formatNumber(data.kd_d, 1) }}</td>
                <td :class="data.kd_k > data.kd_d ? 'text-red' : 'text-green'">
                  {{ data.kd_k > data.kd_d ? '金叉' : '死叉' }}
                </td>
              </tr>
              <tr>
                <td>ADX / DI</td>
                <td>{{ formatNumber(data.adx14) }}</td>
                <td :class="data.adx14 >= 25 ? (data.di_plus > data.di_minus ? 'text-red' : 'text-green') : 'text-yellow'">
                  {{ data.adx14 >= 25 ? '趨勢成立' : data.adx14 < 20 ? '盤整震盪' : '趨勢醞釀' }}
                </td>
              </tr>
              <tr>
                <td>量價分析</td>
                <td>{{ data.divergence[0] }}</td>
                <td :class="data.divergence[0].includes('背離') ? 'text-yellow' : 'text-blue'">
                  {{ data.divergence[0].includes('背離') ? '背離' : '同步' }}
                </td>
              </tr>
              <tr>
                <td>主力警示</td>
                <td>{{ data.force_alert[0] }}</td>
                <td :class="data.force_alert[0].includes('進場') ? 'text-red' : data.force_alert[0].includes('出貨') ? 'text-green' : 'text-blue'">
                  {{ data.force_alert[0].includes('主力') ? '警示' : '正常' }}
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- 風險摘要 -->
        <section class="glass-panel card risk-card">
          <div class="card-header">
            <h3>風險與突破摘要</h3>
          </div>
          <div class="risk-content">
            <div class="risk-item">
              <span class="label">真實波動 (ATR14)</span>
              <span class="value">{{ formatNumber(data.atr14) }}</span>
            </div>
            <div class="risk-item">
              <span class="label">20日突破狀態</span>
              <span class="value">{{ data.breakout_status }}</span>
            </div>
            <div class="risk-item full-width">
              <span class="label">風險評估</span>
              <span class="value highlight">{{ data.risk_note }}</span>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.app-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  margin-bottom: 2rem;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo h1 {
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.badge {
  background: linear-gradient(135deg, var(--accent), #8b5cf6);
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 12px;
  letter-spacing: 1px;
}

.icon-accent {
  color: var(--accent);
}

.search-bar {
  display: flex;
  gap: 8px;
  background: rgba(0, 0, 0, 0.2);
  padding: 6px;
  border-radius: 24px;
  border: 1px solid var(--glass-border);
}

.search-bar input {
  background: transparent;
  border: none;
  color: var(--text-primary);
  padding: 8px 16px;
  outline: none;
  font-size: 1rem;
  width: 250px;
}

.search-bar input::placeholder {
  color: var(--text-secondary);
}

.search-btn {
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 20px;
  padding: 8px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.search-btn:hover {
  background: var(--accent-hover);
  transform: scale(1.05);
}

.search-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}

.header-actions {
  display: flex;
  align-items: center;
  margin-left: 20px;
}

.report-btn {
  background: rgba(59, 130, 246, 0.2);
  color: var(--accent);
  border: 1px solid rgba(59, 130, 246, 0.4);
  padding: 8px 16px;
  border-radius: 20px;
  text-decoration: none;
  font-weight: 600;
  transition: all 0.2s ease;
}

.report-btn:hover {
  background: var(--accent);
  color: white;
  transform: translateY(-2px);
}

.loader {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 6rem 2rem;
  text-align: center;
  color: var(--text-secondary);
}

.empty-icon {
  color: rgba(255,255,255,0.1);
  margin-bottom: 1.5rem;
}

.error-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 1.5rem;
  color: var(--danger);
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.2);
  margin-bottom: 2rem;
}

.dashboard {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
}

.card {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--glass-border);
  padding-bottom: 0.75rem;
}

.card-header h3 {
  font-size: 1.1rem;
  color: var(--text-secondary);
  font-weight: 600;
}

.date {
  font-family: 'Consolas', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

/* Market Card */
.stock-name {
  font-size: 1.8rem;
  margin-bottom: 0.5rem;
}

.stock-name span {
  font-size: 1.2rem;
  color: var(--text-secondary);
  font-weight: 400;
}

.price-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 0.25rem;
}

.price {
  font-size: 3rem;
  font-weight: 700;
  font-family: 'Consolas', monospace;
}

.change {
  font-size: 1.2rem;
  font-weight: 600;
  font-family: 'Consolas', monospace;
}

.subtitle {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
}

.volume-info {
  display: flex;
  gap: 1.5rem;
  padding-top: 1rem;
  border-top: 1px dashed rgba(255,255,255,0.1);
  color: var(--text-secondary);
  font-size: 0.95rem;
}

/* Verdict Card */
.verdict-box {
  padding: 1.5rem;
  border-radius: 12px;
  margin-bottom: 1.5rem;
  flex-grow: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.verdict-text {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.6;
}

.bg-red { background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.3); color: #fca5a5; }
.bg-orange { background: rgba(245, 158, 11, 0.2); border: 1px solid rgba(245, 158, 11, 0.3); color: #fcd34d; }
.bg-blue { background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.3); color: #93c5fd; }
.bg-gray { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); color: #e2e8f0; }

.key-levels {
  display: flex;
  justify-content: space-between;
  background: rgba(0,0,0,0.2);
  padding: 1rem;
  border-radius: 12px;
}

.level-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.level-item .label {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.level-item .value {
  font-family: 'Consolas', monospace;
  font-weight: 600;
  font-size: 1.1rem;
}

.stop-loss .value {
  color: var(--danger);
}

/* Metrics Table */
.metrics-table {
  width: 100%;
  border-collapse: collapse;
}

.metrics-table th,
.metrics-table td {
  padding: 0.75rem 0.5rem;
  text-align: left;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

.metrics-table th {
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
}

.metrics-table td:nth-child(2) {
  font-family: 'Consolas', monospace;
}

.metrics-table td:last-child {
  font-weight: 600;
}

/* Risk Card */
.risk-card {
  grid-column: 1 / -1; /* Span full width */
}

.risk-content {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
}

.risk-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(0,0,0,0.2);
  padding: 1.25rem;
  border-radius: 12px;
}

.risk-item.full-width {
  grid-column: 1 / -1;
}

.risk-item .label {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.risk-item .value {
  font-size: 1.1rem;
  font-weight: 500;
}

.risk-item .value.highlight {
  color: var(--warning);
}
</style>
