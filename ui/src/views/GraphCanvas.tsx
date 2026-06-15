import { useEffect, useRef } from "react"
import {
  fit as fitTransform,
  screenToWorld,
  type Viewport,
} from "@/lib/graphViewport"

export interface CanvasNode {
  id: string
  title: string
  type: string
  x: number
  y: number
}

interface Props<N extends CanvasNode> {
  nodes: N[]
  edges: [N, N][]
  world: { w: number; h: number }
  viewport: Viewport
  colorFor: (type: string) => string
  isVisible: (n: N) => boolean
  focusSet: Set<string> | null
  matchIds: Set<string>
  currentMatchId?: string
  selectedId?: string
  degree: (id: string) => number
  onSelect: (n: N) => void
  onFocus: (id: string) => void
  onOpen: (n: N) => void
  onBackground: () => void
  /** Drag a single node to a new world coordinate (called during pointer move). */
  onDrag: (id: string, x: number, y: number) => void
  /**
   * Pan the whole viewport by a screen-pixel delta (called during background
   * drag and two-finger trackpad pan). #252.
   */
  onPanBy: (dx: number, dy: number) => void
  /** Zoom around a screen-space anchor (cursor). #252. */
  onZoomAt: (anchor: { x: number; y: number }, factor: number) => void
}

/**
 * Imperative <canvas> renderer for large graphs (#194) — used past ~300 nodes
 * where one SVG element per node would thrash the DOM. Draws edges → nodes →
 * labels (only the highest-degree handful, the hovered node, matches and the
 * selection) and hit-tests pointer events by nearest node within a radius.
 *
 * #252: now also handles wheel zoom (with cursor-anchored focal point) and
 * background pan (drag empty space, two-finger trackpad, pinch on macOS).
 */
export function GraphCanvas<N extends CanvasNode>(props: Props<N>) {
  const {
    nodes,
    edges,
    world,
    viewport,
    colorFor,
    isVisible,
    focusSet,
    matchIds,
    currentMatchId,
    selectedId,
    degree,
    onSelect,
    onFocus,
    onOpen,
    onBackground,
    onDrag,
    onPanBy,
    onZoomAt,
  } = props
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const hoverRef = useRef<string | null>(null)
  const nodeDragRef = useRef<string | null>(null)
  const panDragRef = useRef<{ x: number; y: number } | null>(null)
  const movedRef = useRef(false)

  // Convert a pointer event's clientX/Y (relative to viewport) into the
  // canvas's local CSS-pixel coordinate space.
  function localPoint(canvas: HTMLCanvasElement, clientX: number, clientY: number) {
    const rect = canvas.getBoundingClientRect()
    return { x: clientX - rect.left, y: clientY - rect.top }
  }

  // Hit-test a screen point against the visible nodes (returns the closest
  // one within ~12 CSS pixels). Background = null.
  function hitTest(canvas: HTMLCanvasElement, clientX: number, clientY: number) {
    const local = localPoint(canvas, clientX, clientY)
    const w = screenToWorld(viewport, { w: rect(canvas).w, h: rect(canvas).h }, world, local.x, local.y)
    let best: N | null = null
    let bestD = 12 * 12 // within ~12 world units
    for (const n of nodes) {
      if (!isVisible(n)) continue
      const dx = n.x - w.x
      const dy = n.y - w.y
      const d = dx * dx + dy * dy
      if (d < bestD) {
        bestD = d
        best = n
      }
    }
    return { node: best, local }
  }

  function rect(canvas: HTMLCanvasElement) {
    const r = canvas.getBoundingClientRect()
    return { w: r.width, h: r.height }
  }

  // Redraw whenever inputs change (positions, filters, focus, selection, viewport).
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const dpr = window.devicePixelRatio || 1
    const r = rect(canvas)
    canvas.width = Math.round(r.w * dpr)
    canvas.height = Math.round(r.h * dpr)
    const { scale, ox, oy } = fitTransform(world, r)
    const s = scale * viewport.zoom

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, r.w, r.h)
    ctx.translate(ox, oy)
    ctx.scale(s, s)
    ctx.translate(viewport.x, viewport.y)

    // edges
    ctx.lineWidth = 1 / s
    for (const [a, b] of edges) {
      if (!isVisible(a) || !isVisible(b)) continue
      const inFocus = !focusSet || (focusSet.has(a.id) && focusSet.has(b.id))
      ctx.strokeStyle = inFocus
        ? "rgba(120,130,140,0.45)"
        : "rgba(120,130,140,0.07)"
      ctx.beginPath()
      ctx.moveTo(a.x, a.y)
      ctx.lineTo(b.x, b.y)
      ctx.stroke()
    }

    // nodes
    const labelled: N[] = []
    for (const n of nodes) {
      if (!isVisible(n)) continue
      const inFocus = !focusSet || focusSet.has(n.id)
      const isMatch = matchIds.has(n.id)
      const isCurrent = currentMatchId === n.id
      const isSel = selectedId === n.id
      const highlight = isSel || isCurrent
      const r = highlight ? 7 : isMatch ? 6 : 4.5
      ctx.globalAlpha = inFocus ? 1 : 0.15
      ctx.beginPath()
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
      ctx.fillStyle = colorFor(n.type)
      ctx.fill()
      if (highlight || isMatch) {
        ctx.lineWidth = (highlight ? 2.5 : 2) / s
        ctx.strokeStyle = isCurrent ? "#2563eb" : "#111827"
        ctx.stroke()
      }
      if (highlight || isMatch || n.id === hoverRef.current) labelled.push(n)
    }

    // labels: high-degree nodes + anything highlighted/hovered
    const top = [...nodes]
      .filter((n) => isVisible(n) && (!focusSet || focusSet.has(n.id)))
      .sort((a, b) => degree(b.id) - degree(a.id))
      .slice(0, 24)
    ctx.globalAlpha = 1
    ctx.fillStyle = "#374151"
    ctx.font = `${11 / s}px var(--font-body, sans-serif)`
    for (const n of new Set([...top, ...labelled])) {
      if (!isVisible(n)) continue
      ctx.globalAlpha = !focusSet || focusSet.has(n.id) ? 1 : 0.2
      ctx.fillText(n.title, n.x + 7, n.y + 3)
    }
    ctx.globalAlpha = 1
  }, [
    nodes,
    edges,
    viewport,
    world,
    focusSet,
    matchIds,
    currentMatchId,
    selectedId,
    colorFor,
    isVisible,
    degree,
  ])

  function setHoverFromClient(canvas: HTMLCanvasElement, clientX: number, clientY: number) {
    const { node } = hitTest(canvas, clientX, clientY)
    const id = node?.id ?? null
    if (id !== hoverRef.current) {
      hoverRef.current = id
      canvas.title = node
        ? `${node.title} • ${node.type} • ${degree(node.id)} connections`
        : ""
    }
  }

  return (
    <canvas
      ref={canvasRef}
      className="h-full w-full cursor-pointer"
      onPointerDown={(e) => {
        const canvas = canvasRef.current!
        movedRef.current = false
        const { node, local } = hitTest(canvas, e.clientX, e.clientY)
        if (node) {
          nodeDragRef.current = node.id
          onSelect(node)
        } else {
          // Background — start a viewport pan (#252).
          panDragRef.current = local
          ;(e.currentTarget as HTMLCanvasElement).setPointerCapture(e.pointerId)
        }
      }}
      onPointerMove={(e) => {
        const canvas = canvasRef.current!
        if (nodeDragRef.current) {
          movedRef.current = true
          const local = localPoint(canvas, e.clientX, e.clientY)
          const w = screenToWorld(
            viewport,
            rect(canvas),
            world,
            local.x,
            local.y,
          )
          onDrag(nodeDragRef.current, w.x, w.y)
          return
        }
        if (panDragRef.current) {
          movedRef.current = true
          const local = localPoint(canvas, e.clientX, e.clientY)
          onPanBy(local.x - panDragRef.current.x, local.y - panDragRef.current.y)
          panDragRef.current = local
          return
        }
        setHoverFromClient(canvas, e.clientX, e.clientY)
      }}
      onPointerUp={(e) => {
        nodeDragRef.current = null
        panDragRef.current = null
        try {
          ;(e.currentTarget as HTMLCanvasElement).releasePointerCapture(e.pointerId)
        } catch {
          // ignore — capture might not be set
        }
      }}
      onPointerLeave={(e) => {
        nodeDragRef.current = null
        panDragRef.current = null
        hoverRef.current = null
        try {
          ;(e.currentTarget as HTMLCanvasElement).releasePointerCapture(e.pointerId)
        } catch {
          // ignore
        }
      }}
      onClick={(e) => {
        if (movedRef.current) return
        const { node } = hitTest(canvasRef.current!, e.clientX, e.clientY)
        if (node) onFocus(node.id)
        else onBackground()
      }}
      onDoubleClick={(e) => {
        const { node } = hitTest(canvasRef.current!, e.clientX, e.clientY)
        if (node) onOpen(node)
      }}
      onWheel={(e) => {
        e.preventDefault()
        const canvas = canvasRef.current!
        const local = localPoint(canvas, e.clientX, e.clientY)
        // Trackpad pinch (macOS) reports wheel with ctrlKey; treat both as zoom.
        if (e.ctrlKey || e.deltaMode === 0) {
          // Two-finger pan on a trackpad arrives as deltaX/deltaY with
          // deltaMode = 0 (pixels). Use it for pan, not zoom.
          if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
            onPanBy(-e.deltaX, -e.deltaY)
            return
          }
          if (e.deltaY !== 0) {
            // Default mouse-wheel zoom
            const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1
            onZoomAt(local, factor)
          }
        }
      }}
    />
  )
}
