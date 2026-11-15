// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {TerminalEditor} from '../src/components/admin/TerminalEditor';
import {api} from '../src/api';
vi.mock('../src/components/admin/EditorDialog',()=>({EditorDialog:({children}: {children: import('react').ReactNode})=><div>{children}</div>}));
vi.mock('../src/api',()=>({api:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('creates an active perimeter terminal without device mapping, structure or actions',async()=>{
 vi.mocked(api.get).mockImplementation(async path=>path.includes('/policies/')?{global_mode:'DISABLED'}:path==='/api/v1/admin/factories'?[{id:1,code:'ARGANDA',name:'Arganda',timezone:'Europe/Madrid',active:true}]:path==='/api/v1/admin/installation-settings'?{default_factory_code:'ARGANDA',default_factory:{id:1,code:'ARGANDA',name:'Arganda',timezone:'Europe/Madrid',active:true},configuration_error:null}:{workshops:[],subworkshops:[],project_lines:[]});
 vi.mocked(api.post).mockResolvedValue({code:'T100'});
 render(<TerminalEditor terminal={null} actions={[]} factories={[{id:1,code:'ARGANDA',name:'Arganda',timezone:'Europe/Madrid',active:true,created_at:'',updated_at:''}]} initialFactory="ARGANDA" onClose={()=>{}} onSaved={()=>{}}/>);
 fireEvent.click(screen.getByRole('switch',{name:'Perimeter only'}));
 expect((screen.getByLabelText(/Oracle device ID/) as HTMLInputElement).disabled).toBe(true);
 expect((screen.getByLabelText('Automatic entry') as HTMLSelectElement).closest('fieldset')?.disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('Display name'),{target:{value:'Factory gate'}});
 fireEvent.click(screen.getByRole('button',{name:'Create terminal'}));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/admin/terminals',expect.objectContaining({perimeter_only:true,project_line_id:null,action_codes:[],oracle_attributes:{},active:true,exit_policy_mode:'DISABLED'})));
});

const cellTerminal = {
 code:'T0001', name:'Main Clock', factory_code:'ARGANDA', terminal_role:'CELL', external_device_id:'DEVICE-001', identification_mode:'BOTH' as const,
 exit_menu_timeout_seconds:17, reporter_id_type:'RFID', oracle_attributes:{work_cell:'A-01', line:'L1', Plant:'legacy'}, active:true,
 action_codes:['START','EXIT'], provisioned:false, activation_pending:false, exit_policy_mode:'SAME_WORK_CELL' as const,
 effective_exit_policy_mode:'SAME_WORK_CELL' as const, global_exit_policy_mode:'DISABLED' as const,
 workshop_id:1, subworkshop_id:2, project_line_id:3,
};
const cellActions = [
 {code:'START', label:'Start work', state_effect:'ENTER' as const, active:true, requires_subaction:false, subaction_codes:[]},
 {code:'EXIT', label:'Exit', state_effect:'EXIT' as const, active:true, requires_subaction:false, subaction_codes:[]},
];
const cellStructure = {
 workshops:[{id:1,code:'W',description:'Workshop',active:true,oracle_work_area_code:'WA'}],
 subworkshops:[{id:2,code:'S',description:'Subworkshop',workshop_id:1,active:true,oracle_machine_code:'M'}],
 project_lines:[{id:3,code:'P',description:'Project / Line',subworkshop_id:2,active:true,oracle_cell_code:'C'}],
};
const factory = {id:1,code:'ARGANDA',name:'Arganda',timezone:'Europe/Madrid',active:true,created_at:'',updated_at:''};
const configureEditor = () => vi.mocked(api.get).mockImplementation(async path => path.includes('/policies/')?{global_mode:'DISABLED'}:path==='/api/v1/admin/structure'?cellStructure:[]);

it('keeps advanced terminal values mounted through collapse and preserves the complete edit payload',async()=>{
 configureEditor();
 vi.mocked(api.put).mockResolvedValue(cellTerminal);
 render(<TerminalEditor terminal={cellTerminal as never} actions={cellActions as never} factories={[factory]} initialFactory="ARGANDA" onClose={()=>{}} onSaved={()=>{}}/>);
 await screen.findByRole('option',{name:'P · Project / Line'});
 const toggle=screen.getByText('Advanced Configuration');
 fireEvent.click(toggle);
 const timeout=screen.getByLabelText(/Seconds before return/i) as HTMLInputElement;
 fireEvent.change(timeout,{target:{value:'31'}});
 fireEvent.change(screen.getByLabelText(/Work cell/),{target:{value:'B-09'}});
 fireEvent.change(screen.getByLabelText(/Same Terminal Exit/),{target:{value:'SAME_WORK_CELL'}});
 fireEvent.change(screen.getByLabelText(/Oracle device ID/),{target:{value:'DEVICE-CHANGED'}});
 fireEvent.change(screen.getByLabelText(/Integration attributes \(JSON\)/),{target:{value:'{"line":"L2"}'}});
 fireEvent.click(toggle);
 expect((screen.getByLabelText(/Seconds before return/i) as HTMLInputElement).value).toBe('31');
 fireEvent.click(toggle);
 expect((screen.getByLabelText(/Work cell/) as HTMLInputElement).value).toBe('B-09');
 fireEvent.click(screen.getByRole('button',{name:'Save changes'}));
 await waitFor(()=>expect(api.put).toHaveBeenCalled());
 const payload=vi.mocked(api.put).mock.calls[0][1] as Record<string,unknown>;
 expect(payload).toMatchObject({factory_code:'ARGANDA',perimeter_only:false,workshop_id:1,subworkshop_id:2,project_line_id:3,name:'Main Clock',external_device_id:'DEVICE-CHANGED',identification_mode:'BOTH',exit_menu_timeout_seconds:31,oracle_attributes:{Plant:'legacy',line:'L2',work_cell:'B-09'},exit_policy_mode:'SAME_WORK_CELL',active:true,action_codes:['START','EXIT']});
});
