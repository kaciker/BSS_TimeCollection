// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MonitoringPanel} from '../src/components/MonitoringPanel';
import {api} from '../src/api';
vi.mock('../src/api',()=>({api:{get:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks()});
it('shows independent factory and cell states and sends both filters',async()=>{
 vi.mocked(api.get).mockImplementation(async url=>url.includes('/clocks')?[]:{factory_perimeter_enabled:true,total:1,items:[{reporter_id:'001',worker_state:'OUTSIDE',factory_state:'INSIDE',factory_code:'ARGANDA',event:{id:'x',terminal_code:'GATE',event_datetime:'2026-10-20T10:00:00Z',action_label:'Factory entry',delivery_status:'LOCAL_ONLY'}}]} as never);
 render(<MonitoringPanel terminals={[]}/>);
 const factory=await screen.findByLabelText('Estado de fábrica');
 expect(screen.getByText('Outside', {selector:'span'})).toBeTruthy();expect(screen.getByText('Inside', {selector:'span'})).toBeTruthy();
 fireEvent.change(factory,{target:{value:'INSIDE'}});
 fireEvent.change(screen.getByLabelText('Estado de célula'),{target:{value:'OUTSIDE'}});
 fireEvent.click(screen.getByRole('button',{name:'Apply filters'}));
 await waitFor(()=>expect(api.get).toHaveBeenCalledWith(expect.stringContaining('worker_state=OUTSIDE&factory_state=INSIDE')));
});
it('hides factory column and filter when perimeter is disabled, including empty results',async()=>{
 vi.mocked(api.get).mockImplementation(async url=>url.includes('/clocks')?[]:{factory_perimeter_enabled:false,total:0,items:[]} as never);
 render(<MonitoringPanel terminals={[]}/>);
 await screen.findByText('No results match these filters.');
 expect(screen.queryByLabelText('Estado de fábrica')).toBeNull();expect(screen.queryByRole('columnheader',{name:'Estado de fábrica'})).toBeNull();
});
