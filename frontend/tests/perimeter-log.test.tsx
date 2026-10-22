// @vitest-environment jsdom
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {EventInspector} from '../src/components/EventInspector';
import type {EventDetail} from '../src/components/monitoringTypes';
afterEach(()=>{cleanup();localStorage.removeItem("bss-timecollection-language")});
it('identifies perimeter history as local and omits Oracle payload/transmission UI',()=>{
 localStorage.setItem('bss-timecollection-language','es');
 const detail={event:{id:'perimeter:test',event_kind:'PERIMETER',reporter_id:'0001',factory_code:'ARGANDA',terminal_code:'GATE',state_effect:'EXIT',event_datetime:'2026-10-20T10:00:00Z',correlation_id:'correlation',auto_cell_exit_event_id:'cell-exit'},attempts:[],oracle_enabled:false,oracle_payload_preview:null} as EventDetail;
 render(<EventInspector detail={detail} onClose={()=>{}}/>);
 expect(screen.getByText('Solo local')).toBeTruthy();
 expect(screen.getByText('ARGANDA')).toBeTruthy();
 expect(screen.getByText('cell-exit')).toBeTruthy();
 expect(screen.queryByText('Oracle payload preview')).toBeNull();
 expect(screen.queryByText(/not been sent to Oracle yet/)).toBeNull();
});
