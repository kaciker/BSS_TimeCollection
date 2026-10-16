// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from "vitest";
import {cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {StructurePanel} from "../src/components/admin/StructurePanel";
import {api} from "../src/api";

vi.mock("../src/api", () => ({api:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
afterEach(() => {cleanup();vi.clearAllMocks();});

const structure={
  workshops:[{id:1,code:"428",description:"Extrusion",active:true},{id:2,code:"429",description:"Assembly",active:true}],
  subworkshops:[{id:10,workshop_id:1,code:"A",description:"TP",active:true},{id:20,workshop_id:2,code:"A",description:"Assembly A",active:true}],
  project_lines:[{id:100,workshop_id:1,subworkshop_id:10,code:"1",description:"TP1",active:true},{id:200,workshop_id:2,subworkshop_id:20,code:"1",description:"Assembly 1",active:true}],
};

describe("Admin Structure",()=>{
  it("renders scoped duplicate codes and filters by Workshop",async()=>{
    vi.mocked(api.get).mockResolvedValue(structure);
    render(<StructurePanel/>);
    await waitFor(()=>expect(screen.getAllByText("TP1")).toHaveLength(1));
    expect(screen.getAllByText("1")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Filter Workshop"),{target:{value:"1"}});
    expect(screen.getAllByText("1")).toHaveLength(1);
    expect(screen.queryByText("Assembly 1")).toBeNull();
  });
  it("creates a Project / Line under the selected Subworkshop",async()=>{
    vi.mocked(api.get).mockResolvedValue(structure);
    vi.mocked(api.post).mockResolvedValue({id:300});
    render(<StructurePanel/>);
    await waitFor(()=>expect(screen.getByText("TP1")).toBeTruthy());
    fireEvent.click(screen.getByRole("button",{name:"+ Project / Line"}));
    fireEvent.change(screen.getByLabelText("Subworkshop",{selector:"select"}),{target:{value:"10"}});
    fireEvent.change(screen.getByLabelText("Code"),{target:{value:"2"}});
    fireEvent.change(screen.getByLabelText("Description"),{target:{value:"TP2"}});
    fireEvent.click(screen.getByRole("button",{name:"Save"}));
    await waitFor(()=>expect(api.post).toHaveBeenCalledWith("/api/v1/admin/structure/project-lines",{code:"2",description:"TP2",active:true,subworkshop_id:10}));
  });
});
