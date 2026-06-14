import { useEffect, useRef } from "react"

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
  pan: { x: number; y: number }
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
  onDrag: (id: string, x: number, y: number) => void
}

/**
 * Imperative <canvas> renderer for large graphs (#194) — used past ~300 nodes
 * where one SVG element per node would thrash the DOM. Draws edges → nodes →
 * labels (only the highest-degree handful, the hovered node, matches and the
 * selection) and hit-tests pointer events by nearest node within a radius.
 */
export function GraphCanvas<N extends CanvasNode>(props: Props<N>) {
  const {
    nodes,
    edges,
    world,
    pan,
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
  } = props
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const hoverRef = useRef<string | null>(null)
  const dragRef = useRef<string | null>(null)
  const movedRef = useRef(false)

  // Map a screen point (CSS px relative to the canvas) into world coordinates,
  // and back. Uniform scale, centred — keeps the layout undistorted.
  function transform(canvas: HTMLCanvasElement) {
    const rect = canvas.getBoundingClientRect()
    const scale = Math.min(rect.width / world.w, rect.height / world.h)
    const ox = (rect.width - world.w * scale) / 2
    const oy = (rect.height - world.h * scale) / 2
    return { rect, scale, ox, oy }
  }
  function toWorld(canvas: HTMLCanvasElement, clientX: number, clientY: number) {
    const { rect, scale, ox, oy } = transform(canvas)
    const px = clientX - rect.left
    const py = clientY - rect.top
    return {
      x: (px - ox) / scale - pan.x,
      y: (py - oy) / scale - pan.y,
    }
  }
  function hitTest(canvas: HTMLCanvasElement, clientX: number, clientY: number) {
    const { x, y } = toWorld(canvas, clientX, clientY)
    let best: N | null = null
    let bestD = 12 * 12 // within ~12 world units
    for (const n of nodes) {
      if (!isVisible(n)) continue
      const dx = n.x - x
      const dy = n.y - y
      const d = dx * dx + dy * dy
      if (d < bestD) {
        bestD = d
        best = n
      }
    }
    return best
  }

  // Redraw whenever inputs change (positions, filters, focus, selection).
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = Math.round(rect.width * dpr)
    canvas.height = Math.round(rect.height * dpr)
    const scale = Math.min(rect.width / world.w, rect.height / world.h)
    const ox = (rect.width - world.w * scale) / 2
    const oy = (rect.height - world.h * scale) / 2

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, rect.width, rect.height)
    ctx.translate(ox, oy)
    ctx.scale(scale, scale)
    ctx.translate(pan.x, pan.y)

    // edges
    ctx.lineWidth = 1 / scale
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
        ctx.lineWidth = (highlight ? 2.5 : 2) / scale
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
    ctx.font = `${11 / scale}px var(--font-body, sans-serif)`
    for (const n of new Set([...top, ...labelled])) {
      if (!isVisible(n)) continue
      ctx.globalAlpha = !focusSet || focusSet.has(n.id) ? 1 : 0.2
      ctx.fillText(n.title, n.x + 7, n.y + 3)
    }
    ctx.globalAlpha = 1
  }, [
    nodes,
    edges,
    pan,
    world,
    focusSet,
    matchIds,
    currentMatchId,
    selectedId,
    colorFor,
    isVisible,
    degree,
  ])

  return (
    <canvas
      ref={canvasRef}
      className="h-full w-full cursor-pointer"
      onPointerDown={(e) => {
        const canvas = canvasRef.current!
        const hit = hitTest(canvas, e.clientX, e.clientY)
        movedRef.current = false
        if (hit) {
          dragRef.current = hit.id
          onSelect(hit)
        }
      }}
      onPointerMove={(e) => {
        const canvas = canvasRef.current!
        if (dragRef.current) {
          movedRef.current = true
          const { x, y } = toWorld(canvas, e.clientX, e.clientY)
          onDrag(dragRef.current, x, y)
          return
        }
        const hit = hitTest(canvas, e.clientX, e.clientY)
        const id = hit?.id ?? null
        if (id !== hoverRef.current) {
          hoverRef.current = id
          canvas.title = hit
            ? `${hit.title} • ${hit.type} • ${degree(hit.id)} connections`
            : ""
        }
      }}
      onPointerUp={() => {
        dragRef.current = null
      }}
      onPointerLeave={() => {
        dragRef.current = null
        hoverRef.current = null
      }}
      onClick={(e) => {
        if (movedRef.current) return
        const hit = hitTest(canvasRef.current!, e.clientX, e.clientY)
        if (hit) onFocus(hit.id)
        else onBackground()
      }}
      onDoubleClick={(e) => {
        const hit = hitTest(canvasRef.current!, e.clientX, e.clientY)
        if (hit) onOpen(hit)
      }}
    />
  )
}
