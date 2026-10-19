export const ACCESS =
  "mailto:bastien.cochet.pro@gmail.com?subject=Relay%20early%20access&body=Hello%2C%20I%20would%20like%20to%20try%20Relay.";

const thin = " ";

export function count(value: number) {
  return Math.round(value).toLocaleString("en-US").replaceAll(",", thin);
}
