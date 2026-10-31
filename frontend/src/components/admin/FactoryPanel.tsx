import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api";
import type { Factory, InstallationSettings } from "../../types";

const blank = { code: "", name: "", location: "", country: "", timezone: "Europe/Madrid" };

export function FactoryPanel() {
  const [factories, setFactories] = useState<Factory[]>([]);
  const [settings, setSettings] = useState<InstallationSettings | null>(null);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = async () => {
    const [rows, current] = await Promise.all([api.get<Factory[]>("/api/v1/admin/factories"), api.get<InstallationSettings>("/api/v1/admin/installation-settings")]);
    setFactories(rows); setSettings(current);
  };
  useEffect(() => { void refresh().catch(err => setError((err as Error).message)); }, []);
  const create = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try { await api.post<Factory>("/api/v1/admin/factories", form); setForm(blank); await refresh(); setNotice("Factory created."); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const edit = async (factory: Factory) => {
    const name = window.prompt("Factory name", factory.name); if (name === null) return;
    const location = window.prompt("Location", factory.location ?? ""); if (location === null) return;
    const country = window.prompt("Country", factory.country ?? ""); if (country === null) return;
    setBusy(true); setError("");
    try { await api.put(`/api/v1/admin/factories/${factory.id}`, { name, location, country, timezone: factory.timezone }); await refresh(); setNotice("Factory details updated."); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const toggle = async (factory: Factory) => {
    setBusy(true); setError("");
    try { await api.put(`/api/v1/admin/factories/${factory.id}`, { active: !factory.active }); await refresh(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const setDefault = async (code: string) => {
    setBusy(true); setError("");
    try { setSettings(await api.put<InstallationSettings>("/api/v1/admin/installation-settings/default-factory", { factory_code: code })); setNotice(`Installation default factory set to ${code}.`); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return <div className="admin-stack">
    {error && <div className="inline-error" role="alert">{error}</div>}{notice && <div className="success-notice" role="status">{notice}</div>}
    <section className="admin-card admin-form-card"><div className="section-heading"><div><h3>Installation default factory</h3><p>Saved on the server and retained across application redeployments.</p></div></div>
      {settings?.configuration_error && <div className="inline-error" role="alert">{settings.configuration_error}</div>}
      <label>Default factory<select disabled={busy} value={settings?.default_factory_code ?? ""} onChange={event => void setDefault(event.target.value)}><option value="">Select factory</option>{factories.filter(item => item.active).map(item => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}</select></label>
    </section>
    <section className="admin-card resource-list"><div className="section-heading"><div><h3>Factories</h3><p>Stable factory codes cannot be changed after creation.</p></div></div><div className="table-wrap"><table><thead><tr><th>Code</th><th>Name</th><th>Location</th><th>Country</th><th>Timezone</th><th>Status</th><th>Actions</th></tr></thead><tbody>{factories.map(factory => <tr key={factory.id}><td><code>{factory.code}</code></td><td>{factory.name}</td><td>{factory.location || "—"}</td><td>{factory.country || "—"}</td><td>{factory.timezone}</td><td>{factory.active ? "Active" : "Inactive"}</td><td><div className="table-controls"><button className="text-button" disabled={busy} onClick={() => void edit(factory)}>Edit</button><button className="text-button" disabled={busy || (!!settings?.default_factory_code && settings.default_factory_code === factory.code)} onClick={() => void toggle(factory)}>{factory.active ? "Deactivate" : "Activate"}</button></div></td></tr>)}</tbody></table></div></section>
    <section className="admin-card admin-form-card"><div className="section-heading"><div><h3>Add factory</h3><p>Factory codes are unique technical identifiers.</p></div></div><form onSubmit={event => void create(event)}><div className="form-grid"><label>Code<input required maxLength={64} pattern="[A-Za-z0-9_-]+" value={form.code} onChange={event => setForm({ ...form, code: event.target.value.toUpperCase() })} /></label><label>Name<input required maxLength={160} value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} /></label><label>Location<input maxLength={160} value={form.location} onChange={event => setForm({ ...form, location: event.target.value })} /></label><label>Country<input maxLength={80} value={form.country} onChange={event => setForm({ ...form, country: event.target.value })} /></label><label>Timezone<input required maxLength={64} value={form.timezone} onChange={event => setForm({ ...form, timezone: event.target.value })} /></label></div><div className="form-actions"><button className="primary" disabled={busy}>{busy ? "Saving…" : "Create factory"}</button></div></form></section>
  </div>;
}
