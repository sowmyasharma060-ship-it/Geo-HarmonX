import React, { useEffect } from 'react'
import { CircleMarker, MapContainer, Polygon, ScaleControl, TileLayer, Tooltip, ZoomControl, useMap } from 'react-leaflet'

function toPolygonLayers(geometry) {
  if (!geometry?.coordinates) return []
  const polygons = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates]
  return polygons.map((polygon) => polygon.map((ring) => ring.map(([lon, lat]) => [lat, lon])))
}

function getParcelCenter(parcel) {
  if (parcel?.coordinates) return [parcel.coordinates.lat, parcel.coordinates.lon]
  const points = []
  function collect(value) {
    if (!Array.isArray(value)) return
    if (Number.isFinite(value[0]) && Number.isFinite(value[1])) {
      points.push([value[1], value[0]])
      return
    }
    value.forEach(collect)
  }
  collect(parcel?.geometry?.coordinates)
  if (!points.length) return [28.6139, 77.209]
  return [
    points.reduce((sum, point) => sum + point[0], 0) / points.length,
    points.reduce((sum, point) => sum + point[1], 0) / points.length,
  ]
}

function MapFocus({ center }) {
  const map = useMap()

  useEffect(() => {
    map.setView(center, Math.max(map.getZoom(), 17), { animate: false })
  }, [map, center[0], center[1]])

  return null
}

export default function MapView({ parcels, selectedParcel, layers, onSelectParcel, compact = false }) {
  const center = getParcelCenter(selectedParcel)

  return (
    <div className={`map-canvas${compact ? ' map-canvas-compact' : ''}`}>
      <MapContainer center={center} zoom={16} minZoom={3} maxZoom={19} scrollWheelZoom zoomControl={false} zoomAnimation={false} fadeAnimation={false} markerZoomAnimation={false} className="leaflet-map">
        <ZoomControl position="topright" />
        <ScaleControl position="bottomleft" metric imperial={false} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />
        <MapFocus center={center} />
        {parcels.map((parcel) => {
          const selected = parcel.id === selectedParcel?.id
          const cadastral = toPolygonLayers(parcel.geometry)
          const municipal = toPolygonLayers(parcel.municipal_geometry)
          return (
            <React.Fragment key={parcel.id}>
              {layers.cadastral && cadastral.map((shape, index) => (
                <Polygon
                  key={`${parcel.id}-cad-${index}`}
                  positions={shape}
                  pathOptions={{
                    color: selected ? '#4be0df' : '#45b8cf',
                    fillColor: selected ? '#26b8be' : '#32869b',
                    fillOpacity: selected ? 0.27 : 0.14,
                    weight: selected ? 3 : 1.5,
                  }}
                  eventHandlers={{ click: () => onSelectParcel(parcel.id) }}
                >
                  <Tooltip sticky>Parcel {parcel.id} · cadastral boundary</Tooltip>
                </Polygon>
              ))}
              {layers.municipal && municipal.map((shape, index) => (
                <Polygon
                  key={`${parcel.id}-mun-${index}`}
                  positions={shape}
                  pathOptions={{ color: '#ff9d82', fillColor: '#ff806d', fillOpacity: 0.09, weight: 2, dashArray: '7 5' }}
                  eventHandlers={{ click: () => onSelectParcel(parcel.id) }}
                >
                  <Tooltip sticky>Parcel {parcel.id} · municipal boundary</Tooltip>
                </Polygon>
              ))}
              {selected && parcel.coordinates && (
                <CircleMarker
                  center={[parcel.coordinates.lat, parcel.coordinates.lon]}
                  radius={5}
                  pathOptions={{ color: '#f0fffc', fillColor: '#4be0df', fillOpacity: 1, weight: 2 }}
                />
              )}
            </React.Fragment>
          )
        })}
      </MapContainer>
      <div className="map-scale">WGS 84 · EPSG:4326</div>
    </div>
  )
}
