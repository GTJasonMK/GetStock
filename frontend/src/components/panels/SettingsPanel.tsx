"use client";

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/ToastProvider";

type SettingsTab = "datasource" | "ai" | "search" | "general";

type DataSourceConfig = {
  source_name: string;
  name?: string;
  enabled: boolean;
  priority: number;
  failure_threshold: number;
  cooldown_seconds: number;
  api_key?: string | null;
};

type AIConfig = {
  id: number;
  name: string;
  enabled: boolean;
  base_url: string;
  api_key: string;
  model_name: string;
  max_tokens: number;
  temperature: number;
  timeout: number;
};

type SearchEngineStatus = {
  engine: string;
  enabled_keys: number;
  total_keys: number;
  total_daily_limit?: number | null;
  total_used_today: number;
};

type GeneralSettings = {
  refresh_interval?: number;
  tushare_token?: string;
  browser_path?: string;
  alert_frequency?: string;
  summary_prompt?: string;
  question_prompt?: string;
  open_alert?: boolean;
  version_check?: boolean;
  [key: string]: unknown;
};

type AIConfigForm = {
  name: string;
  enabled: boolean;
  base_url: string;
  api_key: string;
  model_name: string;
  max_tokens: number;
  temperature: number;
  timeout: number;
};

const SETTINGS_TABS: Array<{ key: SettingsTab; label: string }> = [
  { key: "ai", label: "AI 配置" },
  { key: "datasource", label: "数据源" },
  { key: "search", label: "搜索引擎" },
  { key: "general", label: "通用设置" },
];

const toNumberOr = (value: unknown, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const toErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
};

const getDataSourceName = (row: { source_name: string; name?: string }): string => {
  const name = String(row.source_name || row.name || "").trim();
  return name;
};

const normalizeDataSource = (raw: unknown): DataSourceConfig | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const sourceName = String(obj.source_name || obj.name || "").trim();
  if (!sourceName) return null;

  return {
    source_name: sourceName,
    name: typeof obj.name === "string" ? obj.name : undefined,
    enabled: obj.enabled !== false,
    priority: toNumberOr(obj.priority, 0),
    failure_threshold: toNumberOr(obj.failure_threshold, 3),
    cooldown_seconds: toNumberOr(obj.cooldown_seconds, 300),
    api_key: typeof obj.api_key === "string" ? obj.api_key : obj.api_key == null ? null : String(obj.api_key),
  };
};

const normalizeAIConfig = (raw: unknown): AIConfig | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const id = toNumberOr(obj.id, NaN);
  if (!Number.isFinite(id)) return null;
  return {
    id,
    name: String(obj.name || ""),
    enabled: obj.enabled !== false,
    base_url: String(obj.base_url || ""),
    api_key: String(obj.api_key || ""),
    model_name: String(obj.model_name || ""),
    max_tokens: toNumberOr(obj.max_tokens, 4096),
    temperature: toNumberOr(obj.temperature, 0.7),
    timeout: toNumberOr(obj.timeout, 60),
  };
};

const normalizeSearchEngine = (raw: unknown): SearchEngineStatus | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const engine = String(obj.engine || "").trim();
  if (!engine) return null;
  return {
    engine,
    enabled_keys: toNumberOr(obj.enabled_keys, 0),
    total_keys: toNumberOr(obj.total_keys, 0),
    total_daily_limit: obj.total_daily_limit == null ? null : toNumberOr(obj.total_daily_limit, 0),
    total_used_today: toNumberOr(obj.total_used_today, 0),
  };
};

// 未配置数据源时的默认展示（与后端 DataSourceManager.DEFAULT_PRIORITY 对齐）
const DEFAULT_DATASOURCE_CONFIGS: DataSourceConfig[] = [
  { source_name: "sina", enabled: true, priority: 0, failure_threshold: 3, cooldown_seconds: 300, api_key: null },
  { source_name: "eastmoney", enabled: true, priority: 1, failure_threshold: 3, cooldown_seconds: 300, api_key: null },
  { source_name: "tencent", enabled: true, priority: 2, failure_threshold: 3, cooldown_seconds: 300, api_key: null },
  { source_name: "tushare", enabled: false, priority: 3, failure_threshold: 3, cooldown_seconds: 300, api_key: null },
];

export default function SettingsPanel() {
  const toast = useToast();
  const [tab, setTab] = useState<SettingsTab>("ai");
  const [dataSources, setDataSources] = useState<DataSourceConfig[]>([]);
  const [aiConfigs, setAIConfigs] = useState<AIConfig[]>([]);
  const [searchEngines, setSearchEngines] = useState<SearchEngineStatus[]>([]);

  // AI配置编辑状态
  const [editingConfig, setEditingConfig] = useState<AIConfig | null>(null);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [deleteConfigConfirm, setDeleteConfigConfirm] = useState<{ id: number; name: string } | null>(null);
  const [configForm, setConfigForm] = useState<AIConfigForm>({
    name: "",
    enabled: true,
    base_url: "",
    api_key: "",
    model_name: "",
    max_tokens: 4096,
    temperature: 0.7,
    timeout: 60,
  });

  // 通用设置
  const [generalSettings, setGeneralSettings] = useState<GeneralSettings | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [ds, configs, engines, settings] = await Promise.all([
        api.getDataSourceConfigs().catch(() => []),
        api.getAIConfigs().catch(() => []),
        api.getSearchEngines().catch(() => ({ engines: [] })),
        api.getSettings().catch(() => null),
      ]);

      const normalizedDataSources = Array.isArray(ds)
        ? ds.map((item) => normalizeDataSource(item)).filter((item): item is DataSourceConfig => !!item)
        : [];
      const normalizedAIConfigs = Array.isArray(configs)
        ? configs.map((item) => normalizeAIConfig(item)).filter((item): item is AIConfig => !!item)
        : [];
      const enginesRaw =
        engines &&
        typeof engines === "object" &&
        Array.isArray((engines as { engines?: unknown[] }).engines)
          ? (engines as { engines: unknown[] }).engines
          : [];
      const normalizedSearchEngines = enginesRaw
        .map((item) => normalizeSearchEngine(item))
        .filter((item): item is SearchEngineStatus => !!item);
      const normalizedSettings = settings && typeof settings === "object"
        ? (settings as GeneralSettings)
        : {};

      // 兼容“DB 里只配置了部分数据源”的情况：依然把所有已知数据源都展示出来，
      // 否则用户会误以为系统只支持 sina，且无法启用 eastmoney/tencent 导致 K 线不可用。
      let merged: DataSourceConfig[] = [];
      if (normalizedDataSources.length > 0) {
        const byName = new Map<string, DataSourceConfig>();
        for (const c of normalizedDataSources) {
          const name = getDataSourceName(c);
          if (!name) continue;
          byName.set(name, c);
        }

        merged = DEFAULT_DATASOURCE_CONFIGS.map((d) => {
          const name = getDataSourceName(d);
          const hit = byName.get(name);
          if (hit) return { ...d, ...hit };
          // 兼容“DB 里只配置了部分数据源”的情况：
          // - 后端对“缺失行”会按方法级默认顺序做兜底（不会把缺失当作禁用）
          // - 这里按默认值展示，用户点“保存”后才会写入配置表形成显式配置
          return { ...d };
        });

        // 兜底：若后端返回了未知数据源，也展示出来（便于未来扩展）
        for (const c of normalizedDataSources) {
          const name = getDataSourceName(c);
          if (!name) continue;
          if (!merged.some((x) => getDataSourceName(x) === name)) merged.push(c);
        }
      } else {
        // DB 未配置任何数据源：按默认优先级展示（与后端一致）
        merged = DEFAULT_DATASOURCE_CONFIGS;
      }

      setDataSources(merged);
      setAIConfigs(normalizedAIConfigs);
      setSearchEngines(normalizedSearchEngines);
      setGeneralSettings(normalizedSettings);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!showConfigModal) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setShowConfigModal(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showConfigModal]);

  const handleResetDataSource = async (name: string) => {
    try {
      await api.resetDataSource(name);
      toast.push({ variant: "success", title: "已重置", message: `数据源「${name}」已重置` });
      fetchData();
    } catch (e: unknown) {
      toast.push({ variant: "error", title: "重置失败", message: toErrorMessage(e, "请稍后重试") });
    }
  };

  const handleSaveDataSource = async (row: DataSourceConfig) => {
    const name = getDataSourceName(row);
    if (!name) return;
    try {
      await api.updateDataSource(name, {
        enabled: !!row.enabled,
        priority: Number(row.priority ?? 0),
        failure_threshold: Number(row.failure_threshold ?? 3),
        cooldown_seconds: Number(row.cooldown_seconds ?? 300),
        api_key: row.api_key ?? null,
      });
      toast.push({ variant: "success", title: "已保存", message: `数据源「${name}」配置已更新` });
      fetchData();
    } catch (e: unknown) {
      toast.push({ variant: "error", title: "保存失败", message: toErrorMessage(e, "请检查配置后重试") });
    }
  };

  // AI配置 CRUD
  const openNewConfigModal = () => {
    setEditingConfig(null);
    setConfigForm({
      name: "",
      enabled: true,
      base_url: "",
      api_key: "",
      model_name: "",
      max_tokens: 4096,
      temperature: 0.7,
      timeout: 60,
    });
    setShowConfigModal(true);
  };

  const openEditConfigModal = (config: AIConfig) => {
    setEditingConfig(config);
    setConfigForm({
      name: config.name || "",
      enabled: config.enabled ?? true,
      base_url: config.base_url || "",
      api_key: config.api_key || "",
      model_name: config.model_name || "",
      max_tokens: config.max_tokens || 4096,
      temperature: config.temperature ?? 0.7,
      timeout: config.timeout || 60,
    });
    setShowConfigModal(true);
  };

  const handleSaveConfig = async () => {
    try {
      if (editingConfig) {
        await api.updateAIConfig(editingConfig.id, configForm);
      } else {
        await api.createAIConfig(configForm);
      }
      setShowConfigModal(false);
      fetchData();
      toast.push({
        variant: "success",
        title: "保存成功",
        message: editingConfig ? "AI 配置已更新" : "AI 配置已创建",
      });
    } catch (e: unknown) {
      toast.push({ variant: "error", title: "保存失败", message: toErrorMessage(e, "请检查配置后重试") });
    }
  };

  const handleDeleteConfig = async (id: number, name?: string) => {
    try {
      await api.deleteAIConfig(id);
      fetchData();
      toast.push({ variant: "success", title: "已删除", message: name ? `已删除「${name}」` : "AI 配置已删除" });
    } catch (e: unknown) {
      toast.push({ variant: "error", title: "删除失败", message: toErrorMessage(e, "请稍后重试") });
    }
  };

  const handleToggleConfig = async (config: AIConfig) => {
    try {
      await api.updateAIConfig(config.id, { enabled: !config.enabled });
      fetchData();
    } catch { /* ignore */ }
  };

  // 通用设置保存
  const handleSaveGeneralSettings = async () => {
    if (!generalSettings) return;
    setSettingsSaving(true);
    try {
      await api.updateSettings(generalSettings);
      toast.push({ variant: "success", title: "保存成功", message: "通用设置已保存" });
    } catch (e: unknown) {
      toast.push({ variant: "error", title: "保存失败", message: toErrorMessage(e, "请检查配置后重试") });
    } finally {
      setSettingsSaving(false);
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">系统设置</h1>

      {/* Tab */}
      <div className="tablist mb-6 w-fit">
        {SETTINGS_TABS.map((t) => (
          <button
            type="button"
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`tab ${tab === t.key ? "tab-active" : "tab-inactive"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* AI 配置 */}
      {tab === "ai" && (
        <div>
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-[var(--text-muted)]">配置AI模型用于智能分析和对话</p>
            <button
              type="button"
              onClick={openNewConfigModal}
              className="btn btn-primary"
            >
              + 新增配置
            </button>
          </div>

          {aiConfigs.length === 0 ? (
            <div className="card p-12 text-center">
              <svg className="w-12 h-12 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
              <p className="text-gray-400 mb-4">暂无AI配置，请添加您的AI模型配置</p>
              <button
                type="button"
                onClick={openNewConfigModal}
                className="btn btn-primary"
              >
                添加AI配置
              </button>
            </div>
          ) : (
            <div className="grid gap-4">
              {aiConfigs.map((config) => (
                <div key={config.id} className="card p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${config.enabled ? "bg-green-500" : "bg-gray-300"}`} />
                      <span className="font-medium text-lg">{config.name || "未命名配置"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleToggleConfig(config)}
                        className={`px-3 py-1 rounded-full text-xs ${config.enabled ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}
                      >
                        {config.enabled ? "已启用" : "已禁用"}
                      </button>
                      <button
                        type="button"
                        onClick={() => openEditConfigModal(config)}
                        className="icon-btn p-1 text-[var(--text-muted)] hover:text-[var(--accent)]"
                        title="编辑"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteConfigConfirm({ id: config.id, name: config.name || "未命名配置" })}
                        className="icon-btn p-1 text-[var(--text-muted)] hover:text-red-600"
                        title="删除"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">模型名称</span>
                      <span className="font-mono">{config.model_name || "-"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">API地址</span>
                      <span className="font-mono truncate max-w-48">{config.base_url || "-"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Temperature</span>
                      <span className="font-mono">{config.temperature ?? 0.7}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Max Tokens</span>
                      <span className="font-mono">{config.max_tokens || 4096}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">超时时间</span>
                      <span className="font-mono">{config.timeout || 60}s</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">API Key</span>
                      <span className="font-mono">{config.api_key ? "******" + config.api_key.slice(-4) : "-"}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 数据源管理 */}
      {tab === "datasource" && (
        <div className="space-y-4">
          {dataSources.length > 0 && !dataSources.some((d) => ["eastmoney", "tencent"].includes(getDataSourceName(d)) && d.enabled) && (
            <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm">
              <div className="font-medium">提示：当前未启用 K 线数据源</div>
              <div className="mt-1">K 线图依赖 <span className="font-mono text-xs">eastmoney/tencent</span>，请启用至少一个并点击「保存」。</div>
            </div>
          )}
          {dataSources.length > 0 && dataSources.every((d) => d.enabled === false) && (
            <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm">
              <div className="font-medium">注意：当前所有数据源均为禁用</div>
              <div className="mt-1">这会导致 K 线/分时等接口返回空数据。建议至少启用：</div>
              <div className="mt-1 font-mono text-xs">sina（分时/快讯兜底），eastmoney 或 tencent（K线）</div>
            </div>
          )}

          <div className="card overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 text-sm text-gray-500">
                <tr>
                  <th className="px-4 py-3 text-left">数据源</th>
                  <th className="px-4 py-3 text-center">启用</th>
                  <th className="px-4 py-3 text-center">优先级</th>
                  <th className="px-4 py-3 text-center">失败阈值</th>
                  <th className="px-4 py-3 text-center">冷却(秒)</th>
                  <th className="px-4 py-3 text-center">操作</th>
                </tr>
              </thead>
              <tbody>
                {dataSources.map((row) => (
                  <tr key={getDataSourceName(row)} className="border-t">
                    <td className="px-4 py-3 font-medium">{getDataSourceName(row)}</td>
                    <td className="px-4 py-3 text-center">
                      <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={!!row.enabled}
                          onChange={(e) => {
                            const enabled = e.target.checked;
                            setDataSources((prev) => prev.map((x) => (getDataSourceName(x) === getDataSourceName(row) ? { ...x, enabled } : x)));
                          }}
                        />
                        <span className={`text-xs ${row.enabled ? "text-green-700" : "text-gray-500"}`}>{row.enabled ? "启用" : "禁用"}</span>
                      </label>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <input
                        type="number"
                        className="w-20 input text-center"
                        value={row.priority ?? 0}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          setDataSources((prev) => prev.map((x) => (getDataSourceName(x) === getDataSourceName(row) ? { ...x, priority: Number.isFinite(v) ? v : 0 } : x)));
                        }}
                      />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <input
                        type="number"
                        className="w-20 input text-center"
                        value={row.failure_threshold ?? 3}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          setDataSources((prev) => prev.map((x) => (getDataSourceName(x) === getDataSourceName(row) ? { ...x, failure_threshold: Number.isFinite(v) ? v : 3 } : x)));
                        }}
                      />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <input
                        type="number"
                        className="w-24 input text-center"
                        value={row.cooldown_seconds ?? 300}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          setDataSources((prev) => prev.map((x) => (getDataSourceName(x) === getDataSourceName(row) ? { ...x, cooldown_seconds: Number.isFinite(v) ? v : 300 } : x)));
                        }}
                      />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button type="button" onClick={() => handleSaveDataSource(row)} className="btn btn-primary text-sm px-3 py-1.5">
                          保存
                        </button>
                        <button type="button" onClick={() => handleResetDataSource(getDataSourceName(row))} className="btn btn-secondary text-sm px-3 py-1.5">
                          重置熔断
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {dataSources.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">暂无数据源配置</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 搜索引擎 */}
      {tab === "search" && (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 text-sm text-gray-500">
              <tr>
                <th className="px-4 py-3 text-left">引擎</th>
                <th className="px-4 py-3 text-center">Key 数量</th>
                <th className="px-4 py-3 text-center">每日限额</th>
                <th className="px-4 py-3 text-center">今日已用</th>
              </tr>
            </thead>
            <tbody>
              {searchEngines.map((e) => (
                <tr key={e.engine} className="border-t">
                  <td className="px-4 py-3 font-medium">{e.engine}</td>
                  <td className="px-4 py-3 text-center">{e.enabled_keys}/{e.total_keys}</td>
                  <td className="px-4 py-3 text-center text-gray-500">{e.total_daily_limit || "-"}</td>
                  <td className="px-4 py-3 text-center text-gray-500">{e.total_used_today}</td>
                </tr>
              ))}
              {searchEngines.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-400">暂无搜索引擎配置</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* 通用设置 */}
      {tab === "general" && generalSettings && (
        <div className="card p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">刷新间隔(秒)</label>
              <input
                type="number"
                value={generalSettings.refresh_interval || 3}
                onChange={(e) => setGeneralSettings({ ...generalSettings, refresh_interval: parseInt(e.target.value) || 3 })}
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tushare Token</label>
              <input
                type="password"
                value={generalSettings.tushare_token || ""}
                onChange={(e) => setGeneralSettings({ ...generalSettings, tushare_token: e.target.value })}
                placeholder="输入Tushare Token"
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">浏览器路径</label>
              <input
                type="text"
                value={generalSettings.browser_path || ""}
                onChange={(e) => setGeneralSettings({ ...generalSettings, browser_path: e.target.value })}
                placeholder="用于爬虫的浏览器路径"
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">提醒频率</label>
              <select
                value={generalSettings.alert_frequency || "always"}
                onChange={(e) => setGeneralSettings({ ...generalSettings, alert_frequency: e.target.value })}
                className="input"
              >
                <option value="always">始终提醒</option>
                <option value="once">每日一次</option>
                <option value="never">从不提醒</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">摘要Prompt</label>
              <textarea
                value={generalSettings.summary_prompt || ""}
                onChange={(e) => setGeneralSettings({ ...generalSettings, summary_prompt: e.target.value })}
                placeholder="AI生成摘要时使用的Prompt"
                rows={3}
                className="input resize-y"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">问答Prompt</label>
              <textarea
                value={generalSettings.question_prompt || ""}
                onChange={(e) => setGeneralSettings({ ...generalSettings, question_prompt: e.target.value })}
                placeholder="AI问答时使用的Prompt"
                rows={3}
                className="input resize-y"
              />
            </div>
            <div className="md:col-span-2 flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={generalSettings.open_alert ?? true}
                  onChange={(e) => setGeneralSettings({ ...generalSettings, open_alert: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <span className="text-sm">开启提醒</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={generalSettings.version_check ?? true}
                  onChange={(e) => setGeneralSettings({ ...generalSettings, version_check: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <span className="text-sm">版本检查</span>
              </label>
            </div>
          </div>
          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={handleSaveGeneralSettings}
              disabled={settingsSaving}
              className="btn btn-primary"
            >
              {settingsSaving ? "保存中..." : "保存设置"}
            </button>
          </div>
        </div>
      )}

      {/* AI配置编辑弹窗 */}
      {showConfigModal && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onMouseDown={() => setShowConfigModal(false)}
        >
          <div
            className="card bg-white p-6 w-full max-w-[520px] max-h-[90vh] overflow-y-auto shadow-xl"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 mb-4">
              <h3 className="text-lg font-semibold">{editingConfig ? "编辑AI配置" : "新增AI配置"}</h3>
              <button type="button" onClick={() => setShowConfigModal(false)} className="icon-btn -mr-2 -mt-2" aria-label="关闭">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">配置名称 *</label>
                <input
                  type="text"
                  value={configForm.name}
                  onChange={(e) => setConfigForm({ ...configForm, name: e.target.value })}
                  placeholder="如: GPT-4o / DeepSeek"
                  className="input"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API Base URL *</label>
                <input
                  type="text"
                  value={configForm.base_url}
                  onChange={(e) => setConfigForm({ ...configForm, base_url: e.target.value })}
                  placeholder="https://api.openai.com/v1"
                  className="input"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API Key *</label>
                <input
                  type="password"
                  value={configForm.api_key}
                  onChange={(e) => setConfigForm({ ...configForm, api_key: e.target.value })}
                  placeholder="sk-..."
                  className="input"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">模型名称 *</label>
                <input
                  type="text"
                  value={configForm.model_name}
                  onChange={(e) => setConfigForm({ ...configForm, model_name: e.target.value })}
                  placeholder="gpt-4o / deepseek-chat"
                  className="input"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={configForm.temperature}
                    onChange={(e) => setConfigForm({ ...configForm, temperature: parseFloat(e.target.value) || 0.7 })}
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Max Tokens</label>
                  <input
                    type="number"
                    min="1"
                    value={configForm.max_tokens}
                    onChange={(e) => setConfigForm({ ...configForm, max_tokens: parseInt(e.target.value) || 4096 })}
                    className="input"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">超时时间(秒)</label>
                <input
                  type="number"
                  min="10"
                  value={configForm.timeout}
                  onChange={(e) => setConfigForm({ ...configForm, timeout: parseInt(e.target.value) || 60 })}
                  className="input"
                />
              </div>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={configForm.enabled}
                  onChange={(e) => setConfigForm({ ...configForm, enabled: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <span className="text-sm">启用此配置</span>
              </label>
            </div>

            <div className="flex gap-2 justify-end mt-6">
              <button
                type="button"
                onClick={() => setShowConfigModal(false)}
                className="btn btn-secondary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveConfig}
                disabled={!configForm.name || !configForm.base_url || !configForm.api_key || !configForm.model_name}
                className="btn btn-primary"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteConfigConfirm}
        title="确认删除该 AI 配置？"
        description={deleteConfigConfirm ? `配置「${deleteConfigConfirm.name}」将被删除，且无法恢复。` : undefined}
        confirmText="删除"
        cancelText="取消"
        variant="danger"
        onCancel={() => setDeleteConfigConfirm(null)}
        onConfirm={() => {
          const id = deleteConfigConfirm?.id;
          const name = deleteConfigConfirm?.name;
          setDeleteConfigConfirm(null);
          if (!id) return;
          handleDeleteConfig(id, name);
        }}
      />
    </div>
  );
}
