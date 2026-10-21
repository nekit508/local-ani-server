"use client"

import {Dispatch, ReactNode, SetStateAction, useEffect, useState} from "react";
import {waited} from "@/api/core";

export default function <T>(
    {
        promiseAction, initialsAction, onOkayAction, onErrorAction, externalState = undefined, deps = []
    } : {
        promiseAction: () => Promise<T>,
        initialsAction: () => ReactNode,
        onOkayAction: (object: T, setter: Dispatch<SetStateAction<T | null | undefined>>, reloader: () => void) => ReactNode,
        onErrorAction: (reloader: () => void) => ReactNode
        externalState?: [T | null | undefined, Dispatch<SetStateAction<T | null | undefined>>] | undefined,
        deps?: any[]
    }
) {
    const [state, setState] = externalState === undefined
        ? useState<T | null | undefined>(undefined)
        : externalState
    const [reloader, setReloader] = useState<number>(0)

    const reload = () => setReloader(reloader+1)

    useEffect(() => {
        setState(undefined)
        waited(promiseAction(), setState)
    }, [reloader, ...deps]);

    return state === null ? onErrorAction(reload) : state === undefined ? initialsAction() : onOkayAction(state, setState, reload)
}