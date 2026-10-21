// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {actionVisualKeys} from '../src/actionVisuals';
import {ActionEditor} from '../src/components/admin/ActionEditor';
import {TerminalPage} from '../src/pages/TerminalPage';
import {api} from '../src/api';
vi.mock('../src/api',()=>({api:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
vi.mock('../src/components/admin/EditorDialog',()=>({EditorDialog:({children}: {children:import('react').ReactNode})=><div>{children}</div>}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const keys=['bocadillo','comida','medico-empresa','formacion','no-productivo','comite-empresa','trabajo-fuera-fabrica','medico','viaje-empresa','examenes','mutua-accidente','comite-seguridad-salud','formacion-fuera-jornada','salida-sindical','huelga','acompanamiento-medico'];
it('offers all sixteen new illustrations and retains every legacy key',()=>{
 render(<ActionEditor action={null} actions={[]} terminals={[]} onClose={()=>{}} onSaved={()=>{}}/>);
 for(const key of keys){
  expect(document.querySelector(`img[src="/action-visuals/${key}.png"]`)).toBeTruthy();
 }
 for(const key of ['factory','break','medical','personal','legal','end-work','no-work']) expect(actionVisualKeys.has(key)).toBe(true);
});
it('renders all new visuals on both action and subaction menus',async()=>{
 localStorage.setItem('bss-timecollection-language','en');
 vi.mocked(api.get).mockResolvedValue({code:'TEST',name:'Test',identification_mode:'KEYPAD',actions:[]});
 const choices=keys.map(key=>({code:key,label:key,visual_key:key}));
 vi.mocked(api.post).mockResolvedValueOnce({flow:'EXIT_REQUIRED',worker_state:'INSIDE',actions:choices}).mockResolvedValueOnce({flow:'SUBACTION_REQUIRED',worker_state:'INSIDE',actions:choices});
 render(<TerminalPage/>);
 fireEvent.click(await screen.findByRole('button',{name:'1',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Continue'}));
 await screen.findByRole('button',{name:'bocadillo',exact:true});
 for(const key of keys) expect(document.querySelector(`.action-illustration[src="/action-visuals/${key}.png"]`)).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'bocadillo',exact:true}));
 await waitFor(()=>expect(api.post).toHaveBeenCalledTimes(2));
 for(const key of keys) expect(document.querySelector(`.action-illustration[src="/action-visuals/${key}.png"]`)).toBeTruthy();
});
