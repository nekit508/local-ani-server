"use client"

import {waited} from "@/api/core";
import {bucket, WorkerState} from "@/api/api";
import {useEffect, useReducer, useRef, useState} from "react";
import WorkerInfo from "@/app/workers/WorkerInfo";

export default function () {
    const [req, setReq] = useState<boolean | undefined>(true)
    const revRef = useRef<number>(0)
    const statesRef = useRef(new Map<number, WorkerState>())
    const abortRef = useRef(new AbortController);
    const [, rerender] = useReducer(_ => _+1, 0);

    useEffect(() => {
        revRef.current = 0
        statesRef.current = new Map<number, WorkerState>()
    }, []);

    useEffect(() => {
        setReq(undefined)
        abortRef.current = new AbortController

        const loop = () => {
            const since = revRef.current
            revRef.current = Date.now()
            waited([bucket<WorkerState>("worker", since), abortRef.current.signal], res => {
                setReq(res.ok)
                if (!res.ok)
                    return

                const states = res.data()
                if (states.length > 0) {

                    const map = statesRef.current
                    for (let state of states) {
                        if (state.soft_deleted)
                            map.delete(state.id)
                        else map.set(state.id, state)
                    }

                    rerender()
                }

                setTimeout(loop, 1000);

            }, e => console.log(String(e)))
        }

        loop()

        return () => abortRef.current.abort()
    }, []);

    return (
        <div className="flex flex-wrap flex-row justify-center items-start gap-8 p-8 w-1/2">
            { req === undefined ? "Loading" : !req ? "Error" : statesRef.current.values().toArray().map(state => {
                return <WorkerInfo key={state.id} state={state}/>
            }) }
        </div>
    )
}