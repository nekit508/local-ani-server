"use client"

import {ComponentType, Dispatch, SetStateAction, useCallback, useEffect, useRef, useState} from "react";
import {waited} from "@/api/core";

export default function <T>(
    {
        promiseAction, Initial, OnOkay, OnError, externalState = undefined, deps = []
    } : {
        promiseAction: () => [Promise<T>, AbortController],
        Initial: ComponentType,
        OnOkay: ComponentType<{object: T, setter: Dispatch<SetStateAction<T | undefined>>, reloader: () => void}>,
        OnError: ComponentType<{reloader: () => void, error: any}>
        externalState?: [T | undefined, Dispatch<SetStateAction<T | undefined>>] | undefined,
        deps?: any[]
    }
) {
    const [ds, dss] = useState<T | undefined>(undefined)
    const [state, setState] = externalState === undefined ? [ds, dss] : externalState
    const [reloader, setReloader] = useState<number>(0)
    const [error, setError] = useState<any>(null)

    const actionRef = useRef(promiseAction)
    const stateRef = useRef(state)

    const reload = useCallback(() => setReloader(prev => prev + 1), [])

    useEffect(() => {
        actionRef.current = promiseAction
        stateRef.current = state
    });

    useEffect(() => {
        setError(null)
        const [promise, controller] = actionRef.current()
        waited([promise, controller.signal], setState, setError)
        return () => controller.abort()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reloader, ...deps]);

    return error !== null ? <OnError error={error} reloader={reload}/> :
        state === undefined ? <Initial/> :
            <OnOkay object={state} setter={setState} reloader={reload}/>
}