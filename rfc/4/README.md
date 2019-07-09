---
domain: gitlab.mero.colo.seagate.com
shortname: 4/KV
name: Entrypoint Server
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Mandar Sawant <mandar.sawant@seagate.com>
---

## Consul KV Schema

### Entrypoint Reply Data

```c
struct m0_ha_entrypoint_rep {
        uint32_t                        hae_quorum;            //XXX
        struct m0_fid_arr               hae_confd_fids;        //XXX
        const char                    **hae_confd_eps;
        struct m0_fid                   hae_active_rm_fid;     //XXX
        char                           *hae_active_rm_ep;      //XXX
        /** Data passed back to client to control query flow */
        enum m0_ha_entrypoint_control   hae_control;
        /* link parameters */
        struct m0_ha_link_params        hae_link_params;       //XXX
        bool                            hae_link_do_reconnect; //XXX
};
```
How do we obtain the data for the fields, marked with `//XXX`, from Clovis?

* entrypoint quorum?
* confd fids
* confd endpoint addresses
* primary RM fid
* primary RM endpoint address