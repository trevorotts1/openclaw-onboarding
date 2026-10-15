// Invalid Remotion-side module (MG-030 lint fixture): the timer is
// reached through an alias, so a name scan for setTimeout calls finds
// nothing. The alias is the finding (dynamic_timer_usage).
const st = setTimeout;

export function arm(): void {
  st(function () {}, 10);
}
