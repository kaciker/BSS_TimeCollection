import { useEffect, useState } from "react";
import { api } from "../../api";
import type { StructureData, StructureItem } from "../../types";
import { useLanguage } from "../../i18n";

type Level = "workshops" | "subworkshops" | "project_lines";
const empty: StructureData = { workshops: [], subworkshops: [], project_lines: [] };
export function StructurePanel() {
  const { t } = useLanguage();
  const labels: Record<Level, string> = { workshops: t("workshop"), subworkshops: t("subworkshop"), project_lines: t("projectLine") };
  const [data, setData] = useState<StructureData>(empty);
  const [error, setError] = useState(""); const [query, setQuery] = useState(""); const [status, setStatus] = useState("");
  const [workshopFilter, setWorkshopFilter] = useState(""); const [subFilter, setSubFilter] = useState("");
  const [editor, setEditor] = useState<{level:Level; item:StructureItem | null} | null>(null);
  const [code, setCode] = useState(""); const [description, setDescription] = useState(""); const [active, setActive] = useState(true);
  const [workshopId, setWorkshopId] = useState(""); const [subId, setSubId] = useState(""); const [busy, setBusy] = useState(false);
  const refresh = () => api.get<StructureData>("/api/v1/admin/structure").then(setData).catch(e=>setError((e as Error).message));
  useEffect(() => { void refresh(); }, []);
  const open = (level:Level, item:StructureItem | null) => { setEditor({level,item});setCode(item?.code??"");setDescription(item?.description??"");setActive(item?.active??true);setWorkshopId(String(item?.workshop_id??""));setSubId(String(item?.subworkshop_id??""));setError(""); };
  const save = async () => {
    if (!editor) return; setBusy(true);setError("");
    const body: Record<string,unknown> = {code:code.trim(),description:description.trim(),active};
    if (editor.level==="subworkshops") body.workshop_id=Number(workshopId);
    if (editor.level==="project_lines") body.subworkshop_id=Number(subId);
    const base = editor.level==="project_lines"?"project-lines":editor.level;
    try { if (editor.item) await api.put(`/api/v1/admin/structure/${base}/${editor.item.id}`,body); else await api.post(`/api/v1/admin/structure/${base}`,body); setEditor(null); await refresh(); }
    catch(e){setError((e as Error).message);} finally {setBusy(false);}
  };
  const toggle = async (level:Level,item:StructureItem) => {
    const base=level==="project_lines"?"project-lines":level;
    try {await api.put(`/api/v1/admin/structure/${base}/${item.id}`,{code:item.code,description:item.description,active:!item.active,...(level==="subworkshops"?{workshop_id:item.workshop_id}:level==="project_lines"?{subworkshop_id:item.subworkshop_id}:{})});await refresh();}catch(e){setError((e as Error).message);}
  };
  const workshop = (id?:number) => data.workshops.find(x=>x.id===id);
  const sub = (id?:number) => data.subworkshops.find(x=>x.id===id);
  const matches = (item:StructureItem,level:Level) => {
    const parentSub=level==="project_lines"?sub(item.subworkshop_id):level==="subworkshops"?item:undefined;
    const parentWorkshop=level==="workshops"?item:workshop(parentSub?.workshop_id);
    return (!status||item.active===(status==="active")) && (!workshopFilter||String(parentWorkshop?.id)===workshopFilter) && (!subFilter||String(parentSub?.id)===subFilter) && `${item.code} ${item.description} ${parentSub?.code??""} ${parentWorkshop?.code??""}`.toLowerCase().includes(query.toLowerCase());
  };
  return <><div className="page-actions"><div className="table-controls">{(["workshops","subworkshops","project_lines"] as Level[]).map(level=><button key={level} className="primary" onClick={()=>open(level,null)}>+ {labels[level]}</button>)}</div></div>
    <section className="admin-card resource-list"><div className="list-toolbar"><input aria-label={t("searchStructure")} placeholder={t("searchCodeDescription")} value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label={t("filterWorkshop")} value={workshopFilter} onChange={e=>{setWorkshopFilter(e.target.value);setSubFilter("");}}><option value="">{t("allWorkshops")}</option>{data.workshops.map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select><select aria-label={t("filterSubworkshop")} value={subFilter} onChange={e=>setSubFilter(e.target.value)}><option value="">{t("allSubworkshops")}</option>{data.subworkshops.filter(x=>!workshopFilter||String(x.workshop_id)===workshopFilter).map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select><select aria-label={t("filterStatus")} value={status} onChange={e=>setStatus(e.target.value)}><option value="">{t("allStatuses")}</option><option value="active">{t("enabled")}</option><option value="inactive">{t("disabled")}</option></select></div>
      <div className="table-wrap"><table><thead><tr><th>{t("level")}</th><th>{t("workshop")}</th><th>{t("subworkshop")}</th><th>{t("projectLine")}</th><th>{t("description")}</th><th>{t("status")}</th><th>{t("actions")}</th></tr></thead><tbody>{(["workshops","subworkshops","project_lines"] as Level[]).flatMap(level=>data[level].filter(item=>matches(item,level)).map(item=>{const s=level==="project_lines"?sub(item.subworkshop_id):level==="subworkshops"?item:undefined;const w=level==="workshops"?item:workshop(s?.workshop_id);return <tr key={`${level}-${item.id}`}><td>{labels[level]}</td><td>{w?.code??"—"}</td><td>{s?.code??"—"}</td><td>{level==="project_lines"?item.code:"—"}</td><td>{item.description}</td><td><span className={`resource-status ${item.active?"is-active":"is-inactive"}`}>{item.active?t("enabled"):t("disabled")}</span></td><td><button className="text-button" onClick={()=>open(level,item)}>{t("edit")}</button><button className="text-button" onClick={()=>void toggle(level,item)}>{item.active?t("deactivate"):t("activate")}</button></td></tr>}))}</tbody></table></div></section>
      {editor&&<div className="admin-card admin-form-card"><h3>{editor.item?t("edit"):t("new")} {labels[editor.level]}</h3><div className="form-grid">{editor.level==="subworkshops"&&<label>{t("workshop")}<select value={workshopId} onChange={e=>setWorkshopId(e.target.value)}><option value="">{t("selectWorkshop")}</option>{data.workshops.filter(x=>x.active||x.id===Number(workshopId)).map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select></label>}{editor.level==="project_lines"&&<label>{t("subworkshop")}<select value={subId} onChange={e=>setSubId(e.target.value)}><option value="">{t("selectSubworkshop")}</option>{data.subworkshops.filter(x=>(x.active&&workshop(x.workshop_id)?.active)||x.id===Number(subId)).map(x=><option key={x.id} value={x.id}>{workshop(x.workshop_id)?.code} / {x.code} · {x.description}</option>)}</select></label>}<label>{t("code")}<input value={code} maxLength={64} onChange={e=>setCode(e.target.value)}/></label><label>{t("description")}<input value={description} maxLength={255} onChange={e=>setDescription(e.target.value)}/></label><label><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/> {t("enabled")}</label></div><div className="form-actions"><button className="secondary" onClick={()=>setEditor(null)}>{t("cancel")}</button><button className="primary" disabled={busy||!code.trim()||!description.trim()||(editor.level==="subworkshops"&&!workshopId)||(editor.level==="project_lines"&&!subId)} onClick={()=>void save()}>{t("save")}</button></div></div>}
      {error&&<div className="inline-error" role="alert">{error}</div>}</>;
}
