export const format = (number) => Number(number).toFixed(2);
export const filename = (name = "") => name.length > 27 ? `${name.slice(0, 15)}…${name.slice(-10)}` : name;
