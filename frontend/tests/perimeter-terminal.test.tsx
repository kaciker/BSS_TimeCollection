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
 expect((screen.getByLabelText('Oracle device ID') as HTMLInputElement).disabled).toBe(true);
 expect((screen.getByLabelText('Automatic entry') as HTMLSelectElement).closest('fieldset')?.disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('Display name'),{target:{value:'Factory gate'}});
 fireEvent.click(screen.getByRole('button',{name:'Create terminal'}));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/admin/terminals',expect.objectContaining({perimeter_only:true,project_line_id:null,action_codes:[],oracle_attributes:{},active:true,exit_policy_mode:'DISABLED'})));
});
