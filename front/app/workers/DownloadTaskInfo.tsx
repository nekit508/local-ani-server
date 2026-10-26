import {DownloadTaskState} from "@/api/api";
import ProgressBar from "@/components/ProgressBar";

export default function ( { state }: { state: DownloadTaskState } ) {
    const work_state = state.error != "" ? 2 : state.worker != -1 ? 1 : 0;
    const work_state_text = work_state == 1 ? "WORKING" : work_state == 2 ? "ERROR" : "QUEUED"
    const work_state_text_color = work_state == 1 ? "text-green-600" : work_state == 2 ? "text-red-400" : "text-orange-400"

    return (
        <div className="flex flex-col justify-start items-start default-cornered w-full p-2 gap-1">
            <div className="flex flex-row w-full justify-start items-center">
                <span className="flex-1 text-xs text-foreground/50 text-left">{ `Task#${state.id}` }</span>
                <span className={`text-xs ${work_state_text_color} text-right`}>{ work_state_text }</span>
            </div>

            <span>
                { `${state.title} (${state.source_title}) Ep. ${state.ordinal} ${state.quality}p` }
            </span>

            { work_state == 1 ? <>
                <ProgressBar progress={state.progress} outerStyle={"default-cornered w-full h-4"}/>

                <span className="text-wrap text-foreground/75 text-[9px]">
                {state.state}
                </span>
            </> : work_state == 2 && <span className="text-xs text-red-400"> { state.error } </span> }


            <span className="text-[9px] text-foreground/25">{ `rev ${state.rev}` }</span>
        </div>
    )
}