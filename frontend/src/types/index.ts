// API 响应类型

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

// 股票相关类型
export interface StockInfo {
  code: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  amount: number;
  high: number;
  low: number;
  open: number;
  prev_close: number;
  market: string;
}

export interface FollowedStock {
  id: number;
  stock_code: string;
  stock_name: string;
  cost_price?: number;
  volume?: number;
  sort_order: number;
  created_at: string;
}

// 市场数据类型
export interface IndustryRank {
  code: string;
  name: string;
  change_percent: number;
  turnover: number;
  leading_stock: string;
  leading_stock_change: number;
}

export interface MoneyFlow {
  code: string;
  name: string;
  main_net_inflow: number;
  main_net_inflow_percent: number;
  super_large_net_inflow: number;
  large_net_inflow: number;
  medium_net_inflow: number;
  small_net_inflow: number;
}

// 资讯类型
export interface NewsItem {
  id: string;
  title: string;
  content?: string;
  source: string;
  publish_time: string;
  url?: string;
}

export interface TelegraphItem {
  id: string;
  content: string;
  publish_time: string;
  level: number;
  subjects?: string[];
}

// AI 相关类型
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AIConfig {
  id: number;
  name: string;
  enabled: boolean;
  model_name: string;
}

// 分组类型
export interface StockGroup {
  id: number;
  name: string;
  description?: string;
  sort_order: number;
  stock_count: number;
}
