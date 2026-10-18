package com.acme.pp.controller.app;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** The SAME mapping as the admin controller, in another package — so the two are one path
 *  until the prefixes separate them, which is the collapse `ruoyi` exhibits: its
 *  `/system/tenant/get-by-website` appears once where two endpoints exist. */
@RestController
@RequestMapping("/orders")
public class AppOrderController {

    @GetMapping("/{id}")
    public String get(String id) {
        return id;
    }
}
