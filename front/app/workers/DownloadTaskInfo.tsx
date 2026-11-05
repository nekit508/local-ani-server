import {DownloadTaskState} from "@/api/api";
import ProgressBar from "@/components/ProgressBar";

function resolve(state: DownloadTaskState) : [number, string, string] {
    if (state.data.working) {
        return [0, "WORKING", "text-green-600"]
    } else if (state.data.error !== null) {
        return [1, "ERROR", "text-red-400"]
    } else {
        return [2, "QUEUED", "text-orange-400"]
    }
}

export default function ( { state }: { state: DownloadTaskState } ) {
    const [work_state, work_state_text, work_state_text_color] = resolve(state)

    return (
        <div className="flex flex-col justify-start items-start default-cornered w-full p-2 gap-1">
            <div className="flex flex-row w-full justify-start items-center">
                <span className="flex-1 text-xs text-foreground/50 text-left">{ `Task#${state.id}` }</span>
                <span className={`text-xs ${work_state_text_color} text-right`}>{ work_state_text }</span>
            </div>

            <span>
                { `${state.data.name}` }
            </span>

            <span className="text-[9px] text-foreground/25">
                { `into ${state.data.output_file}` }
            </span>

            { work_state == 0 && <div className="w-full flex-row">
                <ProgressBar progress={state.data.progress} outerStyle={"default-cornered flex-1 h-4"} text={state.data.speed}/>
            </div> }
            { work_state == 1 && <span className="text-xs text-red-400"> { state.data.error } </span> }

            <span className="text-[9px] text-foreground/25">{ `rev ${state.rev}` }</span>
        </div>
    )
}