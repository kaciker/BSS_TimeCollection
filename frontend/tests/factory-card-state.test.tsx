// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MonitoringPanel} from '../src/components/MonitoringPanel';
import {api} from '../src/api';
vi.mock('../src/api',()=>({api:{get:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks();localStorage.removeItem("bss-timecollection-language")});
it('shows independent factory and cell states and sends both filters',async()=>{
 localStorage.setItem('bss-timecollection-language','es');
 vi.mocked(api.get).mockImplementation(async url=>url.includes('/clocks')?[]:{factory_perimeter_enabled:true,total:1,items:[{reporter_id:'001',worker_state:'OUTSIDE',factory_state:'INSIDE',factory_code:'ARGANDA',event:{id:'x',terminal_code:'GATE',event_datetime:'2026-10-20T10:00:00Z',action_label:'Factory entry',delivery_status:'LOCAL_ONLY'}}]} as never);
 render(<MonitoringPanel terminals={[]}/>);
 const factory=await screen.findByLabelText('Estado de fábrica');
 expect(screen.getByText('Fuera', {selector:'span'})).toBeTruthy();expect(screen.getByText('Dentro', {selector:'span'})).toBeTruthy();
 fireEvent.change(factory,{target:{value:'INSIDE'}});
 fireEvent.change(screen.getByLabelText('Estado de célula'),{target:{value:'OUTSIDE'}});
 fireEvent.click(screen.getByRole('button',{name:'Aplicar filtros'}));
 await waitFor(()=>expect(api.get).toHaveBeenCalledWith(expect.stringContaining('worker_state=OUTSIDE&factory_state=INSIDE')));
});
it('hides factory column and filter when perimeter is disabled, including empty results',async()=>{
 vi.mocked(api.get).mockImplementation(async url=>url.includes('/clocks')?[]:{factory_perimeter_enabled:false,total:0,items:[]} as never);
 render(<MonitoringPanel terminals={[]}/>);
 await screen.findByText('No results match these filters.');
 expect(screen.queryByLabelText('Estado de fábrica')).toBeNull();expect(screen.queryByRole('columnheader',{name:'Estado de fábrica'})).toBeNull();
});
it('opens event details in a scrollable modal and closes with Escape or outside click',async()=>{
 localStorage.setItem('bss-timecollection-language','en');
 const event={id:'event-1',terminal_code:'CLOCK',event_datetime:'2026-10-20T10:00:00Z',action_label:'Exit',delivery_status:'PENDING'};
 vi.mocked(api.get).mockImplementation(async url=>url.includes('/clocks')?[]:url.includes('/events/event-1')?{event:{...event,reporter_id:'001',event_kind:'CELL'},attempts:[],oracle_enabled:false,oracle_payload_preview:{ok:true}}:{factory_perimeter_enabled:false,total:1,items:[{reporter_id:'001',worker_state:'OUTSIDE',event}]} as never);
 render(<MonitoringPanel terminals={[]}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Details'}));
 const dialog=await screen.findByRole('dialog',{name:'Event details'}) as HTMLDialogElement;
 expect(dialog.className).toContain('event-modal-dialog');
 expect(dialog.querySelector('.event-modal')).toBeTruthy();
 fireEvent.keyDown(dialog,{key:'Escape'});
 await waitFor(()=>expect(screen.queryByRole('dialog',{name:'Event details'})).toBeNull());
 fireEvent.click(screen.getByRole('button',{name:'Details'}));
 const second=await screen.findByRole('dialog',{name:'Event details'});
 fireEvent.click(second);
 await waitFor(()=>expect(screen.queryByRole('dialog',{name:'Event details'})).toBeNull());
});
