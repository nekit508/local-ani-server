import {DownloadTaskState, workerRestart, WorkerState} from "@/api/api";
import DownloadTaskInfo from "@/app/workers/DownloadTaskInfo";

export default function ({ state }: { state: WorkerState }) {
    const work_state = state.error ? 1 : state.bad_error ? 2 : state.current_task_id != -1 ? 0 : 3
    const work_state_text = work_state == 0 ? "WORKING" : work_state == 1 ? "ERROR" : work_state == 2 ? "ERROR" : "IDLE"
    const work_state_text_color = work_state == 0 ? "text-green-600" : work_state == 1 ? "text-red-400" : work_state == 2 ? "text-red-900" : "text-orange-400"

    const task_state = state.current_task === undefined ? undefined : state.current_task._type == "DownloadTaskState" ? state.current_task as DownloadTaskState : undefined

    return (
        <div className="flex flex-col justify-start items-start default-cornered p-2 gap-1 w-64">
            <div className="flex flex-row w-full justify-start items-center">
                <span className="flex-1 text-xs text-foreground/50 text-left">{ `Worker#${state.id}` }</span>
                <span className={`text-xs ${work_state_text_color} text-right`}>{ work_state_text }</span>
            </div>

            { task_state !== undefined && <DownloadTaskInfo state={task_state}/> }

            <div className="flex flex-row w-full justify-start items-center">
                <span className="flex-1 text-[9px] text-foreground/25">{ `rev ${state.rev}` }</span>
                { work_state !== 0 && work_state !== 3 && <button className="btn-primary py-0 px-1" onClick={e => {
                    e.preventDefault()
                    // noinspection JSIgnoredPromiseFromCall
                    workerRestart(state.id)
                }}>
                   <span className="text-[9px] text-foreground/25"> RESTART </span>
                </button> }
            </div>
        </div>
    )
}