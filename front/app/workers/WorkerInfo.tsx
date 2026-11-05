import {startWorker, stopWorker, WorkerState} from "@/api/api";

const tmp1 = ["STARTING", "WORKING", "ACTIVE", "PROCESSING_COMMANDS"]
const tmp2 = ["IDLE", "DISABLED", "STOPPED"]

function resolve(state: WorkerState) {
    const name = state.data.phase.phase_name

    if (tmp1.includes(name))
        return [0, name, "text-green-600"]
    else if (tmp2.includes(name))
        return [2, name, "text-orange-400"]
    else if (name == "FAILED")
        return [1, name, "text-red-400"]
    else throw Error(`Invalid phase ${name}`)
}

export default function ({ state }: { state: WorkerState }) {
    const [work_state, work_state_text, work_state_text_color] = resolve(state)

    return (
        <div className="flex flex-col justify-start items-start default-cornered p-2 gap-1 w-64">
            <div className="flex flex-row w-full justify-start items-center">
                <span className="flex-1 text-xs text-foreground/50 text-left">{ `Worker#${state.id}` }</span>
                <span className={`text-xs ${work_state_text_color} text-right`}>{ work_state_text }</span>
            </div>

            <div className="flex flex-row w-full justify-start items-center">
                <span className="flex-1 text-[9px] text-foreground/25">{ `rev ${state.rev}` }</span>
                { !state.data.phase.working && !state.data.phase.alive && <button className="btn-primary py-0 px-1" onClick={e => {
                    e.preventDefault()
                    // noinspection JSIgnoredPromiseFromCall
                    startWorker(state.id)
                }}>
                   <span className="text-[9px] text-foreground/25"> START </span>
                </button> }

                { state.data.phase.alive && <button className="btn-primary py-0 px-1" onClick={e => {
                    e.preventDefault()
                    // noinspection JSIgnoredPromiseFromCall
                    stopWorker(state.id)
                }}>
                   <span className="text-[9px] text-foreground/25"> STOP </span>
                </button> }
            </div>
        </div>
    )
}