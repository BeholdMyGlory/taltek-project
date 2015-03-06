
function splitCoords(coords) {
    coords = coords.split(" ")
    if (coords.length > 1) {
        var lastCoord = coords[coords.length - 1]
        coords[coords.length - 1] = "and"
        return coords.join(", ") + " " + lastCoord
    } else {
        return coords[0]
    }
}

function attr(rootElement, attribute) {
    return rootElement.documentElement.getAttribute(attribute)
}
