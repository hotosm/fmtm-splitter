WITH ns AS (
  select * from "negativespace"
)

,spinalsystem AS(
  select CG_StraightSkeleton(ns.geom) as geom
  from ns
)

select * from spinalsystem