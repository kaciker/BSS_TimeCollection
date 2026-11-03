import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { OracleCatalogue } from "../../types";

type Kind = "work-areas" | "machines" | "cells" | "payroll-time-types";
const empty: OracleCatalogue = {payroll_time_types:[],work_areas:[],machines:[],cells:[]};

export function OracleCataloguePanel() {
  const [data, setData] = useState<OracleCatalogue>(empty);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<{kind:Kind; code:string; description:string; parent_code:string; active:boolean} | null>(null);
  const [importText, setImportText] = useState("");
  const refresh = () => api.get<OracleCatalogue>("/api/v1/admin/structure/oracle-catalogue/admin").then(setData).catch(e=>setError((e as Error).message));
  useEffect(()=>{void refresh();},[]);
  const records = useMemo(()=>[
    ...data.work_areas.map(x=>({kind:"work-areas" as Kind,code:x.code,description:x.description,parent:"—",active:x.active})),
    ...data.machines.map(x=>({kind:"machines" as Kind,code:x.code,description:x.description,parent:x.work_area,active:x.active})),
    ...data.cells.map(x=>({kind:"cells" as Kind,code:x.code,description:x.description,parent:x.machine,active:x.active})),
    ...data.payroll_time_types.map(item=>typeof item === "string" ? ({kind:"payroll-time-types" as Kind,code:item,description:"",parent:"—",active:true}) : ({kind:"payroll-time-types" as Kind,code:item.code,description:item.description??"",parent:"—",active:item.active??true})),
  ].filter(x=>`${x.code} ${x.description} ${x.parent} ${x.kind}`.toLowerCase().includes(query.toLowerCase())),[data,query]);
  const open = (kind:Kind, row?: typeof records[number]) => setEditing({kind,code:row?.code??"",description:row?.description??"",parent_code:row?.parent==="—"?"":row?.parent??"",active:row?.active??true});
  const save = async () => {
    if (!editing) return;
    const body={code:editing.code.trim(),description:editing.description.trim()||null,parent_code:editing.parent_code||null,active:editing.active};
    try {
      const existing=records.some(x=>x.kind===editing.kind&&x.code===editing.code);
      if(existing) await api.put(`/api/v1/admin/structure/oracle-catalogue/${editing.kind}/${encodeURIComponent(editing.code)}`,body);
      else await api.post(`/api/v1/admin/structure/oracle-catalogue/${editing.kind}`,body);
      setEditing(null);setNotice("Oracle catalogue saved.");await refresh();
    } catch(e){setError((e as Error).message);}
  };
  const parentOptions=editing?.kind==="machines"?data.work_areas:editing?.kind==="cells"?data.machines:[];
  const label=(kind:Kind)=>({"work-areas":"WORK_AREA",machines:"MACHINE",cells:"CELL","payroll-time-types":"Payroll Time Type"}[kind]);
  const importCatalogue = async () => {
    try { const payload=JSON.parse(importText); const result=await api.post<{added:number;updated:number;unchanged:number;invalid:number}>("/api/v1/admin/structure/oracle-catalogue/import",payload); setNotice(`Import complete: ${result.added} added, ${result.updated} updated, ${result.unchanged} unchanged.`);setError("");setImportText("");await refresh(); }
    catch(e){setError((e as Error).message);}
  };
  return <>
    <section className="admin-card resource-list">
      <div className="list-toolbar"><input aria-label="Search Oracle catalogue" placeholder="Search catalogue" value={query} onChange={e=>setQuery(e.target.value)}/>{(["work-areas","machines","cells","payroll-time-types"] as Kind[]).map(kind=><button key={kind} className="secondary" onClick={()=>open(kind)}>+ {label(kind)}</button>)}</div>
      <div className="table-wrap"><table><thead><tr><th>Type</th><th>Code</th><th>Description</th><th>Parent</th><th>Status</th><th>Action</th></tr></thead><tbody>{records.map(row=><tr key={`${row.kind}-${row.code}`}><td>{label(row.kind)}</td><td>{row.code}</td><td>{row.description||"—"}</td><td>{row.parent}</td><td>{row.active?"Active":"Inactive"}</td><td><button className="text-button" onClick={()=>open(row.kind,row)}>Edit</button></td></tr>)}</tbody></table></div>
    </section>
    {editing&&<div className="admin-card admin-form-card"><h3>{records.some(x=>x.kind===editing.kind&&x.code===editing.code)?"Edit":"Add"} {label(editing.kind)}</h3><div className="form-grid"><label>Code<input value={editing.code} onChange={e=>setEditing({...editing,code:e.target.value})}/></label>{editing.kind!=="payroll-time-types"&&<label>Description<input value={editing.description} onChange={e=>setEditing({...editing,description:e.target.value})}/></label>}{editing.kind!=="work-areas"&&editing.kind!=="payroll-time-types"&&<label>Parent<select value={editing.parent_code} onChange={e=>setEditing({...editing,parent_code:e.target.value})}><option value="">Select parent</option>{parentOptions.map(item=><option key={item.code} value={item.code}>{item.code} · {item.description}</option>)}</select></label>}<label><input type="checkbox" checked={editing.active} onChange={e=>setEditing({...editing,active:e.target.checked})}/> Active</label></div><div className="form-actions"><button className="secondary" onClick={()=>setEditing(null)}>Cancel</button><button className="primary" disabled={!editing.code.trim()||(editing.kind!=="work-areas"&&editing.kind!=="payroll-time-types"&&!editing.parent_code)} onClick={()=>void save()}>Save</button></div></div>}
    <section className="admin-card"><h2>Import the full HR-Path catalogue</h2><p>Convert all enabled rows from the four workbook tabs to the canonical JSON document. The import validates hierarchy and upserts records without deleting omitted entries.</p><label>Catalogue JSON<textarea rows={10} value={importText} onChange={e=>setImportText(e.target.value)} placeholder='{"work_areas":[...],"machines":[...],"cells":[...],"payroll_time_types":[...]}' /></label><button className="primary" disabled={!importText.trim()} onClick={()=>void importCatalogue()}>Validate and import</button><details><summary>Format example</summary><pre>{`{"work_areas":[{"code":"439","description":"Acabado TP","active":true}],"machines":[{"code":"4391","description":"T439.1","work_area_code":"439","active":true}],"cells":[{"code":"54T","description":"G.V. P24","machine_code":"4391","active":true}],"payroll_time_types":[{"code":"Workshop Entry ES","active":true}]}`}</pre></details></section>
    {notice&&<div className="success-notice" role="status">{notice}</div>}{error&&<div className="inline-error" role="alert">{error}</div>}
  </>;
}
