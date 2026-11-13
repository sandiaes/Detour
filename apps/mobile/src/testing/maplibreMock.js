// The native MapLibre views cannot run in Jest. This stand-in renders plain views and records what
// the app asked the map to do, so tests can check markers, lines, style and camera.
const React = require("react");
const { Pressable, View } = require("react-native");

const state = {
  map: null,
  fitBounds: jest.fn(),
  easeTo: jest.fn(),
  sources: {},
  layers: [],
  reset() {
    this.map = null;
    this.fitBounds.mockClear();
    this.easeTo.mockClear();
    this.sources = {};
    this.layers = [];
  },
};

function Map(props) {
  state.map = props;
  return React.createElement(View, { testID: "map" }, props.children);
}

function Camera({ ref }) {
  React.useImperativeHandle(ref, () => ({ fitBounds: state.fitBounds, easeTo: state.easeTo }));
  return null;
}

function Marker({ id, onPress, children }) {
  return React.createElement(
    Pressable,
    { testID: `marker-${id}`, onPress: () => onPress && onPress({ nativeEvent: { id } }) },
    children,
  );
}

function GeoJSONSource({ id, data, children }) {
  state.sources[id] = data;
  return React.createElement(View, { testID: `source-${id}` }, children);
}

function Layer(props) {
  state.layers = state.layers.filter((l) => l.id !== props.id).concat([props]);
  return null;
}

module.exports = { __mock: state, Map, Camera, Marker, GeoJSONSource, Layer };
